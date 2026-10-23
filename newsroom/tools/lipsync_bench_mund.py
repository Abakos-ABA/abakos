"""Mundoeffnung (MediaPipe FaceMesh, CPU) gegen Ton-Huellkurve: Korrelation bei Versatz -10..+10 Bildern. Aufruf: video wav"""
import sys, subprocess, os, numpy as np, wave, cv2, mediapipe as mp
v, w = sys.argv[1], sys.argv[2]
cap = cv2.VideoCapture(v); fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=False)
o = []
while True:
    ok, f = cap.read()
    if not ok: break
    r = fm.process(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    if r.multi_face_landmarks:
        l = r.multi_face_landmarks[0].landmark; o.append(abs(l[14].y - l[13].y) / max(1e-6, abs(l[291].x - l[61].x)))
    else: o.append(o[-1] if o else 0)
o = np.array(o); x = wave.open(w); a = np.frombuffer(x.readframes(x.getnframes()), np.int16).astype(float)
e = np.array([np.sqrt((a[i*640:(i+1)*640]**2).mean()) for i in range(len(a)//640)]); n = min(len(o), len(e)); o, e = o[:n], np.log1p(e[:n])
best = max(((np.corrcoef(o[max(0,k):n+min(0,k)], e[max(0,-k):n-max(0,k)])[0,1], k) for k in range(-10, 11)))
c0 = np.corrcoef(o, e)[0,1]
print(os.path.basename(v), "corr@0 %.2f best %.2f @ %d Bilder, Oeffnung mean %.3f std %.3f" % (c0, best[0], best[1], o.mean(), o.std()))
