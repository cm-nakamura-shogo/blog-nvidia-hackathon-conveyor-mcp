import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
plt.rcParams['font.family']=['Hiragino Sans','sans-serif']
fig,ax=plt.subplots(figsize=(10.5,5.6))
ax.set_xlim(0,104); ax.set_ylim(0,56); ax.axis('off')
def box(x,y,w,h,fc,ec,label=None,fs=11,tc='#1a202c',bold=False):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.3,rounding_size=1.2',fc=fc,ec=ec,lw=1.6))
    if label: ax.text(x+w/2,y+h/2,label,ha='center',va='center',fontsize=fs,color=tc,fontweight='bold' if bold else 'normal')
box(2,22,13,12,'#edf2f7','#4a5568','Jetson',12,bold=True)
box(22,4,44,44,'#e6fffa','#2c7a7b')
ax.text(44,44.5,'Arduino UNO + Grove ベースシールド',ha='center',fontsize=11.5,fontweight='bold',color='#234e52')
ax.text(44,41.2,'シールドを UNO の上に重ねて挿す・電圧スイッチは 5V',ha='center',fontsize=9,color='#285e61')
ax.plot([15,22],[28,28],lw=2.2,color='#4a5568')
ax.text(18.5,29.6,'USB',ha='center',fontsize=9.5,color='#4a5568')
ax.text(18.5,25.3,'通信＋給電',ha='center',fontsize=8.5,color='#4a5568')
ports=['D2','D3','D4','D5','D6','D7','D8']
names={'D6':'3台目','D7':'1台目','D8':'2台目'}
ys={}
for i,p in enumerate(ports):
    y=35-i*4.4
    on=p in names
    box(52,y,9,3.0,'#f6ad55' if on else '#ffffff','#c05621' if on else '#a0aec0',p,10,tc='#1a202c' if on else '#a0aec0',bold=on)
    ys[p]=y+1.5
ax.text(56.5,5.6,'Grove コネクタ（デジタル）',ha='center',fontsize=8.5,color='#285e61')
relay_y={'D6':33,'D7':20,'D8':7}
for p,ry in relay_y.items():
    box(72,ry,13,7,'#fefcbf','#b7791f','Grove - Relay',9.5)
    ax.plot([61.3,72],[ys[p],ry+3.5],lw=2,color='#c05621')
    box(90,ry,12,7,'#edf2f7','#4a5568',f'コンベア\n{names[p]}',9.5)
    ax.plot([85.3,90],[ry+3.5,ry+3.5],lw=2.6,color='#2d3748')
    ax.text(87.6,ry+4.6,'12V',ha='center',fontsize=7.5,color='#2d3748')
ax.text(87,43.5,'Grove ケーブルで挿すだけ（HIGH で ON）',ha='center',fontsize=9,color='#c05621')
fig.savefig(sys.argv[1],dpi=150,bbox_inches='tight')
