import intrms
import numpy as np
import matplotlib.pyplot as plt
import os
import re
import csv

# GRUPOS:
#       QB - Quadrupolos e dipolos
#       S - Sextupolos
#       CO - COrretoras
#       TRIM - TRIM coils

data_dir = "/home/controle/Downloads/Scope - 04-05-2022 104512/Scope/SI/"
date = "{}-{}-{}{} {}:{}:{}".format(*re.findall("\d\d", data_dir))  # noqa: W605

groupdict = {
    "QB": ["Dipolos e Quadrupolos", "SI-Fam:PS-[QB].*"],
    "S": ["Sextupolos", "SI-Fam:PS-S.*"],
    "CO": ["Corretores", "SI-{}\w\d:PS-(CH|CV|QS).*"],  # noqa: W605
    "TRIM": ["Trim Coils", "SI-{}\w\d:PS-Q[^S].*"],  # noqa: W605
}

while True:
    group = input("Digite o grupo de fontes (QB, S, CO ou TRIM): ")
    if group in ["CO", "TRIM"]:
        sector = input("Digite o setor: ")
    else:
        sector = ""

    name_pattern = groupdict[group][1].format(sector)

    flist = [f for f in os.listdir(data_dir) if re.match(name_pattern, f)]
    print(flist)
    names = []
    y = []

    for fname in flist:
        with open(data_dir + fname) as file:
            reader = csv.reader(file)
            next(reader)  # skip row
            names.append(next(reader)[1])
            param = float(next(reader)[1][1:-1].split(" ")[0])
            fs = float(next(reader)[1])

        data_1 = np.loadtxt(data_dir + fname, delimiter=",", skiprows=6, usecols=0)
        if len(data_1.shape) < 2:
            data_1 = np.expand_dims(data_1, axis=1)

        dataRMS, f_sel = intrms.intrms(data_1, fs)
        y_index = np.where(f_sel <= 100)[0][-1] - 1
        y.append(dataRMS[y_index, 0] / param * 1e6)

    # ploting
    x = np.arange(len(names))
    fig, ax = plt.subplots()
    bars = ax.bar(x, y, zorder=3)
    ax.set_ylabel("Ruído integrado [ppm]")
    ax.set_xlabel("Fonte")
    ax.set_xticks(x, names, rotation=45, ha="right", rotation_mode="anchor", size=8)
    ax.bar_label(bars, padding=3, rotation=90, size=8)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.grid(axis="y", zorder=0)

    plt.title(
        "Ruído integrado até 100Hz de fontes de {} ({})".format(groupdict[group][0], date),
        size=10,
        pad=40,
    )
    plt.tight_layout()
    plt.show()
