from threading import Thread
from queue import Queue
import os
from datetime import datetime
import smtplib
import siriuspy.search as sirius
from zipfile import ZipFile, ZIP_DEFLATED
import ssl
import epics
import tempfile
from getpass import getpass

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

PV_TIMEOUT = 0.5
SAMPLE_FREQ = 4000


class PS:
    def __init__(self, name: str):
        self.name = name
        self.sample_freq = SAMPLE_FREQ

        if epics.caget(name + ":OpMode-Sts", timeout=PV_TIMEOUT) != 3:
            raise RuntimeError("{} operation mode is not SlowRef".format(name))

        addr = 0xD008
        self.model = sirius.PSSearch.conv_psname_2_psmodel(name)

        if self.model == "FBP":
            if epics.caget(name + ":SOFBMode-Sts", timeout=PV_TIMEOUT) != 0:
                raise RuntimeError("{} SOFB mode status is true".format(name))

            addr = self.get_fbp_addr()
            self.sample_freq /= 4
        elif self.model in ["FAC_DCDC", "FAP"]:
            addr = 0xD006

        self.initial_sample_freq = epics.caget(name + ":ScopeFreq-RB", timeout=PV_TIMEOUT)
        self.initial_scope = epics.caget(name + ":ScopeSrcAddr-RB", timeout=PV_TIMEOUT)
        self.initial_trigger = epics.caget(name + ":Src-Sel", timeout=PV_TIMEOUT)

        self.wfm = []
        self.max_ref = epics.caget(name + ":ParamCtrlMaxRef-Cte", timeout=PV_TIMEOUT)

        epics.caput(name + ":ScopeFreq-SP", self.sample_freq)
        epics.caput(name + ":ScopeSrcAddr-SP", addr)
        epics.caput(name + ":Src-Sel", "Study")

        self.sample_freq = epics.caget(name + ":ScopeFreq-RB", timeout=PV_TIMEOUT)

    def get_fbp_addr(self):
        for index, ps in enumerate(
            sirius.PSSearch.conv_udc_2_bsmps(sirius.PSSearch.conv_psname_2_udc(self.name))
        ):
            if self.name == ps[0]:
                return index * 2

    def acquire_and_set_wfm(self):
        self.wfm = epics.caget(self.name + ":Wfm-Mon", timeout=PV_TIMEOUT * 10)

    def __del__(self):
        epics.caput(self.name + ":ScopeFreq-SP", self.initial_sample_freq)
        epics.caput(self.name + ":ScopeSrcAddr-SP", self.initial_scope)
        epics.caput(self.name + ":Src-Sel", self.initial_trigger)


def get_pss(index: int, ps_names: list, q: Queue):
    pss = []
    for ps in ps_names:
        try:
            pss.append(PS(ps))
        except RuntimeError:
            continue

    q.put({str(index): pss})


def save_data(path: str = "", recipient: str = ""):
    if not path:
        path = os.getcwd()

    root_name = "Scope"
    root = os.path.join(path, root_name)

    os.mkdir(root)

    print("Getting PV information and setting them up...")

    q = Queue()
    locs = ["TS", "TB", "BO", "SI"]
    threads = []
    ps_dict = {}

    for loc in locs:
        os.mkdir(os.path.join(root, loc))
        sub_args = sirius.PSSearch.get_psnames({"sec": loc, "dev": "(?!FC).*"})

        pivot_divider = 2 if loc != "SI" else 6

        pivot = len(sub_args) // pivot_divider
        for i in range(0, pivot_divider):
            t = Thread(
                target=get_pss,
                args=(
                    i,
                    sub_args[pivot * i : pivot * (i + 1) if i < pivot_divider else len(sub_args)],
                    q,
                ),
            )
            print(pivot * i, pivot * (i + 1))
            t.start()

            threads.append(t)

        for t in threads:
            t.join()

        ps_dict[loc] = list(q.get().values())[0]
        for i in range(1, pivot_divider):
            ps_dict[loc] += list(q.get().values())[0]
        print(ps_dict[loc])

    epics.caput("AS-RaMO:TI-EVG:StudyExtTrig-Cmd", 1)
    wfm_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    print("Getting PS waveforms at {}...".format(wfm_time))

    for loc, pss in ps_dict.items():
        for ps in pss:
            ps.acquire_and_set_wfm()
            with open(os.path.join(root, loc, ps.name + ".csv"), "w") as csv_file:
                csv_file.write("Date,{}\n".format(wfm_time))
                csv_file.write("Name,{}\n".format(ps.name))
                csv_file.write("Param Ctrl Max Ref,{}\n".format(ps.max_ref))
                csv_file.write("Sample Freq,{}\n".format(ps.sample_freq))
                csv_file.write("Model,{}\n".format(ps.model))

                csv_file.writelines("Wfm-Mon\n" + "\n".join([str(wfm) for wfm in ps.wfm]))

    if recipient:
        message = MIMEMultipart()
        message["From"] = ""
        message["To"] = recipient
        message["Subject"] = "Scope Values"

        with tempfile.SpooledTemporaryFile() as tp:
            with ZipFile(tp, "w", ZIP_DEFLATED) as zip:
                for dir in ["Scope/TS", "Scope/TB", "Scope/BO", "Scope/SI"]:
                    for file in os.listdir(dir):
                        zip.write(os.path.join(dir, file))

            tp.seek(0)

            part = MIMEBase("application", "octet-stream")
            part.set_payload(tp.read())

            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment; filename= {}".format("{} - {}.zip".format(root_name, wfm_time)),
            )

            message.attach(part)
            text = message.as_string()
            context = ssl.create_default_context()
            password = getpass("Enter your email password: ")
            with smtplib.SMTP("smtp.office365.com", 587) as server:
                server.starttls(context=context)
                server.login(recipient, password)
                server.sendmail(recipient, recipient, text)
