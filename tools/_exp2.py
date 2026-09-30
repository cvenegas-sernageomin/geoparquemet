import numpy as np,cv2,sys
import ra3d
S=sys.argv[1]
zs=np.load(ra3d.CACHE/'zs_exp.npy'); zb=np.load(ra3d.CACHE/'zb_exp.npy')
foto=cv2.imread(str(ra3d.CACHE/'foto_exp.png'))
col={0:(60,60,230),1:(230,100,60),2:(40,200,230)}   # BGR r,b,y
def formas(banda,r):
    with np.errstate(invalid='ignore'):
        dif=np.abs(zs-zb[None]); ok=np.isfinite(zb)[None]&np.isfinite(zs)&(dif<banda)
    # reparto por cercanía a la cámara entre planos que afloran
    zz=np.where(ok,zs,np.inf); ganador=np.argmin(zz,0); hay=np.isfinite(zz.min(0))
    out=[]
    for i in range(3):
        m=((ganador==i)&hay).astype(np.uint8)
        k=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2*r+1,2*r+1))
        m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,k); m=cv2.morphologyEx(m,cv2.MORPH_OPEN,k)
        n,et,st,_=cv2.connectedComponentsWithStats(m,connectivity=4)
        if n>1: m=(et==1+np.argmax(st[1:,cv2.CC_STAT_AREA])).astype(np.uint8)
        m=cv2.GaussianBlur(m.astype(np.float32),(0,0),r/2)>0.5
        out.append(m)
    return out
pan=[]
for banda,r in ((1.2,7),(0.6,9),(0.35,11)):
    im=foto.copy()
    for i,m in enumerate(formas(banda,r)):
        ov=im.copy(); ov[m]=col[i]; im=cv2.addWeighted(ov,.45,im,.55,0)
        cnt,_=cv2.findContours(m.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE); cv2.drawContours(im,cnt,-1,col[i],2)
    cv2.putText(im,f'banda {banda}',(10,30),0,1,(255,255,255),2); pan.append(im[0:800,100:750])
cv2.imwrite(S+'/formas.jpg',np.hstack(pan))
