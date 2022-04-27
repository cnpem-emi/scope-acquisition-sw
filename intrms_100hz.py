from matplotlib.contour import QuadContourSet
import intrms
import numpy as np
import matplotlib.pyplot as plt
import os
import re
import csv

# GROUPS:
#       QB - Quadrupoles and dipoles
#       S - Sextupoles
#       COR - CORrectors
#       TRIM - TRIM coils

data_dir = 'Scope - 18-04-2022 161458/Scope/SI/'

while(True):
    group=input("Digite o grupo de fontes (QB, S, COR ou TRIM): ")
    if group in ['COR', 'TRIM']:
        sector = input("Digite o setor: ")
        if group == "COR":
            name_pattern =  "SI-"+sector+"[MC][1-4]:PS-(CH|CV|QS).*"
        elif group == "TRIM":
            name_pattern = "SI-"+sector+"[MC][1-4]:PS-Q[^S].*"
    else:
        name_pattern = "SI-Fam:PS-["+group+"].*"

    
    flist = [f for f in os.listdir(data_dir) if re.match(name_pattern, f)]
    names = []
    y = []

    for fname in flist:
        with open(data_dir+fname) as file:
            reader = csv.reader(file)
            next(reader)    #skip row
            names.append(next(reader)[1])
            param = float(next(reader)[1][1:-1].split(" ")[0])
            fs=float(next(reader)[1])
            
        data_1 = np.loadtxt(data_dir+fname, delimiter=',', skiprows=6, usecols = 0)
        if(len(data_1.shape)<2):
            data_1 = np.expand_dims(data_1, axis=1)

        dataRMS, f_sel = intrms.intrms(data_1, fs)
        y_index = np.where(f_sel>100)[0][0]-1
        y.append(dataRMS[y_index, 0]/param*1e6)

    # ploting
    x = np.arange(len(names))
    fig, ax = plt.subplots()
    bars = ax.bar(x, y)
    ax.set_ylabel("Ruído integrado até 100Hz [ppm]")
    ax.set_xlabel("Fonte")
    ax.set_xticks(x, names, rotation=45, ha='right', rotation_mode='anchor', size=8)
    ax.bar_label(bars, padding=3, rotation=90)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    plt.tight_layout()
    plt.show()
