import intrms
import numpy as np
import matplotlib.pyplot as plt
import os
import re
import csv


import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()

data_dir = filedialog.askdirectory() + "/SI/"

date = "{}-{}-{}{} {}:{}:{}".format(*re.findall("\d\d", data_dir))  # noqa: W605

group_dict = {
    1: ["Dipoles and Quadrupoles", "SI-Fam:PS-[QB].*"],
    2: ["Sextupoles", "SI-Fam:PS-S.*"],
    3: ["Correctors Sector {:02d}", "SI-{:02d}\w\d:PS-(CH|CV|QS).*"],  # noqa: W605
    4: ["Trim-Coils Sector {:02d}", "SI-{:02d}\w\d:PS-Q[^S].*"],  # noqa: W605
}


def plot_bars():
    names = []
    y = []
    for file_name in file_list:
        with open(data_dir + file_name) as file:
            reader = csv.reader(file)
            next(reader)  # skip row
            names.append(next(reader)[1])
            param = float(next(reader)[1][1:-1].split(" ")[0])
            fs = float(next(reader)[1])

        data_1 = np.loadtxt(data_dir + file_name, delimiter=",", skiprows=6, usecols=0)
        if len(data_1.shape) < 2:
            data_1 = np.expand_dims(data_1, axis=1)

        dataRMS, f_sel = intrms.intrms(data_1, fs)
        y_index = np.where(f_sel <= f_max)[0][-1] - 1
        y.append(dataRMS[y_index, 0] / param * 1e6)

    x = np.arange(len(names))
    fig, ax = plt.subplots()
    bars = ax.bar(x, y, zorder=3)
    ax.set_ylabel("Integrated noise [ppm]")
    ax.set_xlabel("Power supply")

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(top=max(y) * 1.2)
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.grid(axis="y", zorder=0)

    for i, val in enumerate(y):
        plt.text(i - 0.25, val * 1.1, "{:.4f}".format(val), rotation="vertical")

    plt.title(
        "Integrated noise up to {}Hz of {} supplies \n{}".format(f_max, group_dict[group][0].format(sector), date),
        size=10,
        pad=40,
    )
    plt.tight_layout()
    return


while True:
    f_max = float(input("Type the maximum frequency [Hz] for noise integration: "))
    group = int(input("""
0: Cancel
1: Dipoles e Quadrupoles
2: Sextupoles
3: Correctors
4: Trim-Coils
5: All

Type a group of power supplies: """))

    if group == 0:
        break

    if group == 5:
        os.mkdir(os.path.join(data_dir, "Plots/"))
        save_dir = data_dir + "Plots/"
        print("Saving plots to " + save_dir + " ...")
        for group in range(1, 5):
            if group == 3 or group == 4:
                sector_list = [j for j in range(1, 21)]
            else:
                sector_list = [""]
            for sector in sector_list:
                name_pattern = group_dict[group][1].format(sector)
                file_list = [f for f in os.listdir(data_dir) if re.match(name_pattern, f)]
                plot_bars()
                plt.savefig(save_dir + group_dict[group][0].format(sector))
                plt.close()
        print("done!")

    else:
        if group == 3 or group == 4:
            sector = int(input("Type a sector: "))
        else:
            sector = ""

        name_pattern = group_dict[group][1].format(sector)
        file_list = [f for f in os.listdir(data_dir) if re.match(name_pattern, f)]
        plot_bars()
        plt.show()
