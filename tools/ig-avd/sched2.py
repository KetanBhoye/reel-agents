# IG 456.1 flow: audio page -> Use audio -> gallery -> Next -> caption -> Trial -> wheel schedule -> Schedule
import sys,json,time,datetime as dt,igctl as g
s=json.load(open(sys.argv[1])); t=dt.datetime.strptime(s['when'],'%Y-%m-%d %H:%M')
def home():
    for _ in range(6):
        if g.find('feed_tab'): return
        g.back(); time.sleep(1.5)
        if g.find('Start over'): g.tap('Start over'); time.sleep(2)
        if g.find('Discard',exact=True): g.tap('Discard',exact=True); time.sleep(2)
home()
g.push_as_newest(s['file'])
if s.get('own'):
    g.tap('feed_tab'); time.sleep(2); g.tap('action_bar_left_button'); time.sleep(5)
    if g.find('cam_dest_clips'): g.tap('cam_dest_clips'); time.sleep(4)
elif s.get('audio_page'):
    g.open_url(s['audio_page']); time.sleep(10)
else:
    g.open_url(s['ref']); time.sleep(12)
    g.tap_xy(540,1000); time.sleep(2)
    g.tap_xy(370,1965); time.sleep(8)
g.shot('x_audio')
if not s.get('own'): g.tap_xy(285,656); time.sleep(8)
if not s.get('own') and not g.find('gallery_preview_button'):
    if g.find('auxiliary_button'): g.tap('auxiliary_button'); time.sleep(4)
if not s.get('own') and not g.find('gallery_preview_button'): g.shot('x_fail'); raise SystemExit('not on camera after Use audio')
print('music:',[g.label(n) for n in g.nodes() if 'music_attribution' in g.label(n)])
if not s.get('own'): g.tap('gallery_preview_button'); time.sleep(6)
print('picked',g.pick_newest()); time.sleep(8)
g.tap('clips_right_action_button'); time.sleep(12)
g.wait_for('caption_input_text_view',25)
g.tap('caption_input_text_view'); time.sleep(2)
g.paste_into('caption_input_text_view', s['caption']); time.sleep(2)
g.tap_xy(995,139); time.sleep(3)
g.set_trial(True); time.sleep(2)
if g.find('Close',exact=True): g.tap('Close',exact=True); time.sleep(2)
for _ in range(3):
    if g.find('More options'): break
    g.swipe(540,1800,540,900); time.sleep(1)
g.tap('More options'); time.sleep(3)
sc=g.find('Schedule this reel')[0]; g.tap_xy(970,(sc['b'][1]+sc['b'][3])//2)
g.wait_for('numberpicker_input')
g.set_picker(0,t.strftime('%a, %b %d')); g.set_picker(3,t.strftime('%p'))
g.set_picker(1,str(int(t.strftime('%I')))); g.set_picker(2,t.strftime('%M'))
got=[n['t'] for n in g.nodes() if n['r']=='numberpicker_input']; print('picker',got)
g.tap('Done',exact=True); time.sleep(3)
g.shot('x_more')
hq=g.find('Upload at highest quality')[0]; y=(hq['b'][1]+hq['b'][3])//2
if sum(g.pixel(925,y))>=150: g.tap_xy(970,y); time.sleep(1.5)
g.tap_xy(75,135); time.sleep(3)
for _ in range(3):
    tr=g.find('Trial',exact=True)
    if tr: break
    g.swipe(540,900,540,1600); time.sleep(1.5)
ns=g.nodes()
tg=min([n for n in ns if n['r']=='toggle'], key=lambda n: abs(n['b'][1]-tr[0]['b'][1]))
btn=[g.label(n) for n in ns if n['r']=='share_button']
g.swipe(540,700,540,1700); time.sleep(1.5)
cap=[n['t'] for n in g.nodes() if n['r']=='caption_input_text_view']
print('TRIAL',tg['k'],'BUTTON',btn,'CAPTION',cap)
g.shot('x_final')

if '--go' in sys.argv and tg['k'] and btn==['Schedule | share_button']:
    g.tap_xy(797,2224); time.sleep(7)
    for lab in ('Turn off and share','Turn off and schedule'):
        if g.find(lab): g.tap(lab); time.sleep(4)
    time.sleep(8); g.shot('x_after'); print('SCHEDULED')
