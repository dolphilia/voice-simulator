#!/usr/bin/env python3
"""母音/F0条件を平均に潰さず可視化する。"""
import argparse
import json
import os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR",str(ROOT/".cache/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--campaign",default="ans-pilot-v1");args=parser.parse_args()
    path=ROOT/"results"/args.campaign
    data=json.loads((path/"p2-search.json").read_text())
    plt.rcParams["font.family"]="Hiragino Sans"
    matrices=[];names=[]
    for backend in ("B9","G40","dsp","vtl"):
        if backend in ("B9","G40"):
            cells=[r for r in data["fixed_controls"] if r["backend"]==backend]
        else:
            winner=next(r for r in data["chosen"] if r["backend"]==backend)
            cells=next(r["cells"] for r in data["settings"] if r["candidate_id"]==winner["candidate_id"])
        matrix=np.full((5,3),np.nan)
        for i,v in enumerate("aiueo"):
            for j,f0 in enumerate((160,220,300)):
                values=[c["residual"] for c in cells if c["task"]==f"vowel-{v}-{f0}" and c["residual"] is not None]
                if values:matrix[i,j]=np.mean(values)
        matrices.append(matrix);names.append(backend)
    upper=float(np.nanmax(matrices))
    fig,axes=plt.subplots(1,4,figsize=(12,4),layout="constrained")
    for ax,name,values in zip(axes,names,matrices):
        im=ax.imshow(values,vmin=0,vmax=upper,cmap="Blues",aspect="auto")
        ax.set_title(name);ax.set_xticks(range(3),[160,220,300]);ax.set_yticks(range(5),list("aiueo"));ax.set_xlabel("基本周波数（Hz）")
        for (i,j),v in np.ndenumerate(values):ax.text(j,i,f"{v:.2f}" if np.isfinite(v) else "欠損",ha="center",va="center",color="white" if v>upper*.6 else "black",fontsize=10)
    axes[0].set_ylabel("母音")
    fig.colorbar(im,ax=axes,label="対数帯域比の平均二乗残差")
    fig.suptitle("開発群での帯域残差：自然さ・明瞭性の合格点ではない",fontsize=13)
    fig.savefig(path/"vowel-residuals.svg")
    fig.savefig(path/"vowel-residuals.png",dpi=180)
    plt.close(fig)


if __name__=="__main__":main()
