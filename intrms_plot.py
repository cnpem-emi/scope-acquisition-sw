import intrms
import numpy as np
import matplotlib.pyplot as plt

import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()

data_file = filedialog.askopenfilename()

data_1 = np.loadtxt(data_file, delimiter=",", skiprows=6, usecols=0)
if len(data_1.shape) < 2:
    data_1 = np.expand_dims(data_1, axis=1)

dataRMS, f_sel = intrms.intrms(data_1, 205)
f_sel = np.atleast_2d(f_sel[1:]).T
# np.savetxt("scope_intrms.csv", np.concatenate((f_sel, dataRMS), axis=1), delimiter=",")

plt.loglog(f_sel, dataRMS)
plt.xlabel("Frequency [Hz]")
plt.ylabel("Integrated spectrum")
plt.show()
