import json,sys,numpy as np,cv2
from PIL import Image,ImageOps
import ra3d,capas_ar_nuevas as N
V,F,*_=ra3d.malla(); tr,sup=ra3d.interpretacion()
nombre=sys.argv[1]; d=N.NUEVAS[nombre]; c=N.camara(d)
L=1000; esc=L/max(c['w'],c['h']); w,h=round(c['w']*esc),round(c['h']*esc)
e4=esc/2; zb=cv2.resize(ra3d.zbuffer(c,V,F,round(c['w']*e4),round(c['h']*e4),e4),(w,h),interpolation=cv2.INTER_NEAREST)
fam={'Frac1':'r','Frac4':'b','Frac5':'y','Frac51_1':'y','Frac 5-3':'y'}
zs={}
for n,(Vs,Fs) in sup.items():
    z=ra3d.raster_superficie(c,Vs,Fs,w,h,esc); k=fam[n]; zs[k]=np.minimum(zs.get(k,np.inf),z)
np.save(ra3d.CACHE/'zs_exp.npy',np.stack([zs[k] for k in 'rby'])); np.save(ra3d.CACHE/'zb_exp.npy',zb)
foto=ImageOps.exif_transpose(Image.open(ra3d.RAIZ/'Fotos y modelos'/'Fotos Terreno 30-09-26'/nombre)).convert('RGB').resize((w,h))
foto.save(ra3d.CACHE/'foto_exp.png'); print(w,h)
for k in 'rby':
    dif=zs[k]-zb; ok=np.isfinite(dif); print(k,ok.sum(),np.percentile(np.abs(dif[ok]),[5,25,50,75]))
