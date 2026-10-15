import glob,json,re,sys
from rapidocr_onnxruntime import RapidOCR
o=RapidOCR();R={}
for d in "hv":
    R[d]={}
    for f in sorted(glob.glob(f"qa/{d}/*.png")):
        r,_=o(f);R[d][f[-7:-4]]=" | ".join(x[1] for x in (r or []))
json.dump(R,open("qa/ocr.json","w"),indent=0)
for d in "hv":
    a=" ".join(R[d].values())
    print(d,{t:a.count(t) for t in ["79,700","26,004","0.62","14.93","Recall plan","est.","Biggest audience","synthetic","FalkorDB"]})
    print(d,"SECRET-HITS",re.findall(r"(?i)AIza\w+|api.?key|password|secret",a))
    print(d,"BANNED",re.findall(r"(?i)every place it spread|first ever|nobody",a))
