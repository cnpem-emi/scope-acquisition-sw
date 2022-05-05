import os
import smtplib
import ssl
import tempfile
import time
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from getpass import getpass
from queue import Queue
from threading import Thread
from zipfile import ZIP_DEFLATED, ZipFile

import epics
import siriuspy.search as sirius

PV_TIMEOUT = 2
SAMPLE_FREQ = 4000

TRIGGER_NAMES = [
    "TB-Glob:TI-Mags",
    "TS-Glob:TI-Mags",
    "BO-Glob:TI-Mags-Fams",
    "BO-Glob:TI-Mags-Corrs",
    "SI-Glob:TI-Mags-Bends",
    "SI-Glob:TI-Mags-Quads",
    "SI-Glob:TI-Mags-Sexts",
    "SI-Glob:TI-Mags-Skews",
    "SI-Glob:TI-Mags-Corrs",
    "SI-Glob:TI-Mags-QTrims",
]


class PS:
    def __init__(self, name: str):
        self.name = name
        self.sample_freq = SAMPLE_FREQ

        op_mode_pv = epics.PV(name + ":OpMode-Sts")
        op_mode_pv.wait_for_connection(PV_TIMEOUT)

        if op_mode_pv.value is None or op_mode_pv.value > 4:
            raise RuntimeError("{} operation mode is not SlowRef".format(name))

        addr = 0xD008
        self.model = sirius.PSSearch.conv_psname_2_psmodel(name)

        if self.model == "FBP":
            sofb_mode_pv = epics.PV(name + ":SOFBMode-Sts")
            if sofb_mode_pv.value != 0:
                raise RuntimeError("{} SOFB mode status is true".format(name))

            addr = self.get_fbp_addr()
            self.sample_freq /= 4
        elif self.model in ["FAC_DCDC", "FAP"]:
            addr = 0xD006

        scope_freq_pv = epics.PV(name + ":ScopeFreq-RB")
        scope_freq_sp_pv = epics.PV(name + ":ScopeFreq-SP")
        scope_addr_pv = epics.PV(name + ":ScopeSrcAddr-RB")
        scope_addr_sp_pv = epics.PV(name + ":ScopeSrcAddr-SP")
        auto_trig_sel_rb = epics.PV(name + ":WfmUpdateAuto-Sts")
        auto_trig_sel_sp = epics.PV(name + ":WfmUpdateAuto-Sel")
        wfm_max_ref_pv = epics.PV(name + ":ParamCtrlMaxRef-Cte")

        scope_freq_pv.wait_for_connection(PV_TIMEOUT)
        scope_freq_sp_pv.wait_for_connection(PV_TIMEOUT)
        scope_addr_pv.wait_for_connection(PV_TIMEOUT)
        scope_addr_sp_pv.wait_for_connection(PV_TIMEOUT)
        wfm_max_ref_pv.wait_for_connection(PV_TIMEOUT)
        auto_trig_sel_rb.wait_for_connection(PV_TIMEOUT)
        auto_trig_sel_sp.wait_for_connection(PV_TIMEOUT)

        self.auto_trig = auto_trig_sel_rb.value
        self.initial_sample_freq = scope_freq_pv.value
        self.initial_scope = scope_addr_pv.value

        self.wfm = []

        self.max_ref = wfm_max_ref_pv.value

        scope_freq_sp_pv.value = self.sample_freq
        scope_addr_sp_pv.value = addr
        auto_trig_sel_sp.value = 1

        self.sample_freq = scope_freq_pv.value

    def get_fbp_addr(self):
        for index, ps in enumerate(
            sirius.PSSearch.conv_udc_2_bsmps(sirius.PSSearch.conv_psname_2_udc(self.name))
        ):
            if self.name == ps[0]:
                return 0xD000 + index * 2

    def acquire_and_set_wfm(self):
        wfm_pv = epics.PV(self.name + ":Wfm-Mon")
        wfm_pv.wait_for_connection(PV_TIMEOUT)

        self.wfm = wfm_pv.value

    def recover_initial_config(self):
        scope_freq_pv = epics.PV(self.name + ":ScopeFreq-SP")
        scope_addr_pv = epics.PV(self.name + ":ScopeSrcAddr-SP")
        auto_trig_sel_sp = epics.PV(self.name + ":WfmUpdateAuto-Sel")

        auto_trig_sel_sp.wait_for_connection(PV_TIMEOUT)
        scope_freq_pv.wait_for_connection(PV_TIMEOUT)
        scope_addr_pv.wait_for_connection(PV_TIMEOUT)

        auto_trig_sel_sp.value = self.auto_trig
        scope_freq_pv.value = self.initial_sample_freq
        scope_addr_pv.value = self.initial_scope


def get_pss(index: int, ps_names: list, q: Queue):
    pss = []
    for ps in ps_names:
        try:
            pss.append(PS(ps))
        except RuntimeError:
            continue

    q.put({str(index): pss})


def save_data(path: str = ""):
    if not path:
        path = os.getcwd()

    recipient = input("Enter your email address: ")

    root_name = "Scope {}".format(datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
    root = os.path.join(path, root_name)

    os.mkdir(root)

    print("Getting PV information and setting them up...")

    q = Queue()
    locs = ["TS", "TB", "BO", "SI"]
    threads = []
    ps_dict = {}

    trigger_pvs = [
        [
            epics.PV(trigger + ":Src-Sel"),
            epics.PV(trigger + ":Src-Sts"),
            epics.PV(trigger + ":State-Sel"),
            epics.PV(trigger + ":State-Sts"),
        ]
        for trigger in TRIGGER_NAMES
    ]
    old_trig_srcs = {}
    for pv in trigger_pvs:
        for val in pv:
            val.wait_for_connection(PV_TIMEOUT)
        old_trig_srcs[pv[0].pvname] = pv[1].value
        old_trig_srcs[pv[2].pvname] = pv[3].value
        pv[0].value = "Study"
        pv[2].value = 1

    for loc in locs:
        print("{}...".format(loc), end="", flush=True)
        os.mkdir(os.path.join(root, loc))
        sub_args = sirius.PSSearch.get_psnames({"sec": loc, "dis": "PS", "dev": "(?!FC).*"})

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
            t.start()

            threads.append(t)

        for t in threads:
            t.join()

        ps_dict[loc] = list(q.get().values())[0]
        for i in range(1, pivot_divider):
            ps_dict[loc] += list(q.get().values())[0]
        print("done!")

    trig_pv = epics.PV("AS-RaMO:TI-EVG:StudyExtTrig-Cmd")
    trig_pv.wait_for_connection(PV_TIMEOUT)
    trig_pv.value = 1
    print("Waiting for data acquisition...")
    time.sleep(5)

    wfm_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    print("Getting PS waveforms at {}...".format(wfm_time))

    for loc, pss in ps_dict.items():
        print("{}...".format(loc), end="", flush=True)
        for ps in pss:
            ps.acquire_and_set_wfm()
            ps.recover_initial_config()
            with open(os.path.join(root, loc, ps.name + ".csv"), "w") as csv_file:
                csv_file.write("Date,{}\n".format(wfm_time))
                csv_file.write("Name,{}\n".format(ps.name))
                csv_file.write("Param Ctrl Max Ref,{}\n".format(ps.max_ref))
                csv_file.write("Sample Freq,{}\n".format(ps.sample_freq))
                csv_file.write("Model,{}\n".format(ps.model))

                csv_file.writelines("Wfm-Mon\n" + "\n".join([str(wfm) for wfm in ps.wfm]))
        print("done!")

    for pv in trigger_pvs:
        pv[0].value = old_trig_srcs[pv[0].pvname]
        pv[2].value = old_trig_srcs[pv[2].pvname]

    if recipient:
        message = MIMEMultipart()
        message["From"] = ""
        message["To"] = recipient
        message["Subject"] = "Scope Values"

        with tempfile.SpooledTemporaryFile() as tp:
            with ZipFile(tp, "w", ZIP_DEFLATED) as zip:
                for dir in [
                    "{}/TS".format(root_name),
                    "{}/TB".format(root_name),
                    "{}/BO".format(root_name),
                    "{}/SI".format(root_name),
                ]:
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
            print("File sent to {}!".format(recipient))


if __name__ == "__main__":
    save_data()
