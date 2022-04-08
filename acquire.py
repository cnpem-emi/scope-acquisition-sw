import os
from datetime import datetime
import smtplib
import siriuspy.search as sirius
from zipfile import ZipFile
import ssl
import epics
import tempfile

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart


class PS:
    def __init__(self, name: str, sample_freq: float):
        if epics.get_pv(name + ":SOFBMode-Sts", timeout=1) != "False":
            raise RuntimeError("{} SOFB mode status is true".format(name))

        if epics.get_pv(name + ":OpMode-Sts", timeout=1) != "SlowRef":
            raise RuntimeError("{} operation mode is not SlowRef".format(name))

        self.name = name
        self.sample_freq = sample_freq

        self.initial_sample_freq = epics.caget(name + ":ScopeFreq-RB")
        self.initial_scope = epics.caget(name + ":ScopeSrcAddr-RB")
        self.initial_trigger = epics.caget(name + ":Src-Sel")

        self.wfm = []
        self.max_ref = epics.get_pv(name + ":ParamCtrlMaxRef-Cte", timeout=1)

        addr = 0xD008
        self.model = sirius.PSSearch.conv_psname_2_psmodel(name)

        if self.model == "FBP":
            addr = self.get_fbp_addr()
            self.sample_freq /= 4
        elif self.model in ["FAC_DCDC", "FAP"]:
            addr = 0xD006

        epics.caput(name + ":ScopeFreq-SP", self.sample_freq)
        epics.caput(name + ":ScopeSrcAddr-SP", addr)
        epics.caput(name + ":Src-Sel", "Study")

    def get_fbp_addr(self):
        for index, ps in enumerate(
            sirius.PSSearch.conv_udc_2_bsmps(sirius.PSSearch.conv_psname_2_udc(self.name))
        ):
            if self.name == ps[0]:
                return index * 2

    def acquire_and_set_wfm(self):
        self.wfm = epics.get_pv(self.name + ":Wfm-Mon", timeout=1)

    def __del__(self):
        epics.caput(self.name + ":ScopeFreq-SP", self.initial_sample_freq)
        epics.caput(self.name + ":ScopeSrcAddr-SP", self.initial_scope)
        epics.caput(self.name + ":Src-Sel", self.initial_trigger)


def save_data(sample_freq: float, path: str = "", recipient: str = ""):
    ps_dict = {}

    if not path:
        path = os.getcwd()

    root_name = "Scope"
    root = os.path.join(path, root_name)

    os.mkdir(root)

    for loc in ["TS", "TB", "BO", "SI"]:
        ps_dict[loc] = []
        os.mkdir(os.path.join(root, loc))
        for ps in sirius.PSSearch.get_psnames({"sec": loc}):
            ps_dict[loc].append(PS(ps, sample_freq))

    epics.caput("AS-RaMO:TI-EVG:StudyExtTrig-Cmd", 1)
    wfm_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

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
        # email message
        message = MIMEMultipart()
        message["From"] = ""
        message["To"] = recipient
        message["Subject"] = "Scope Values"

        with tempfile.SpooledTemporaryFile() as tp:
            with ZipFile(tp, "w") as zip:
                for root, _, files in os.walk(root):
                    for file in files:
                        zip.write(os.path.join(root, file))

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
            password = input("Enter your email password")
            with smtplib.SMTP("smtp.office365.com", 587) as server:
                server.starttls(context=context)
                server.login(recipient, password)
                server.sendmail(recipient, recipient, text)
