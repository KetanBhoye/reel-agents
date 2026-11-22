import sys,time,igctl as g
P={1:(658,1065),2:(744,1152),3:(776,1270),4:(744,1388),5:(658,1474),6:(540,1506),7:(422,1474),8:(335,1388),9:(304,1270),10:(335,1152),11:(422,1065),12:(540,1034)}
h,m,ap=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
g.tap_xy(540,2072); time.sleep(3)
g.tap_xy(*P[h]); time.sleep(1.5)
g.tap_xy(*P[12 if m==0 else m//5]); time.sleep(1.5)
g.tap('am_label' if ap=='AM' else 'pm_label'); time.sleep(1)
print([g.label(n) for n in g.nodes() if n['r'] in ('hours','minutes') or (n['r'] in ('am_label','pm_label') and n['k'])])
g.tap('button1'); time.sleep(2)
