import os, re, subprocess, threading, uuid, requests
from flask import Flask, request, jsonify
from datetime import datetime

app=Flask(__name__)
RECORD_DIR="/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs={}
HTML_PAGE="""
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V12 FINAL</title>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:20px}input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}button{background:linear-gradient(90deg,#22c55e,#16a34a);color:#fff;font-weight:bold}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #22c55e}.card.error{border-color:#ef4444}.card.done{border-color:#22c55e}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:12px;max-height:400px}.ok{color:#22c55e;font-weight:bold}</style>
</head><body>
<h2>BIGO V12 <span style="background:#22c55e;color:#000;padding:4px 10px;border-radius:20px;font-size:12px">FINAL FIX</span></h2>
<p style="color:#aaa">แกะ slink + ดึง HLS จากหน้าไลฟ์โดยตรง</p>
<input id="url" placeholder="วาง slink.bigovideo.tv">
<select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="status" class="ok"></div><div id="list"></div>
<script>
function extractUrl(t){let m=t.match(/https?:\/\/[^\s]+/);if(m) return m[0].replace(/[)"'】。]+$/, '');return t.trim();}
async function start(){
 let raw=document.getElementById('url').value;if(!raw){alert('วางลิงก์ก่อน');return;}
 let url=extractUrl(raw);document.getElementById('status').innerHTML='กำลังแกะ... '+url;
 let q=document.getElementById('q').value;
 let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,quality:q})});let j=await r.json();
 document.getElementById('status').innerHTML='OK ID '+j.id+'<br>Resolved:'+j.resolved.slice(0,80)+'<br>SiteID:'+j.siteid+'<br>HLS:'+(j.hls?'เจอแล้ว!':'กำลังหา');
 load();
}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{
 let cls=it.status=='done'?'done':(it.status=='error'?'error':'');
 h+='<div class="card '+cls+'"><b>'+it.resolved.slice(0,100)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+' - '+it.quality+' - Site:'+it.siteid+'</small><pre>'+(it.log||'')+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
"""
HEADERS={
 "User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
 "Referer":"https://www.bigo.tv/",
 "Origin":"https://www.bigo.tv",
 "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
 "Accept-Language":"en-US,en;q=0.9"
}
def resolve_slink(url):
 log=""
 if "slink.bigovideo.tv" in url:
  try:
   s=requests.Session()
   r=s.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
   log+=f"slink GET -> {r.status_code} final:{r.url[:120]}\n"
   if "bigo.tv" in r.url and "slink" not in r.url:
    return r.url, log
   txt=r.text
   pats=[r'https://www\.bigo\.tv/sid/[^\s"\'<>]+', r'"canonical" href="([^"]+bigo\.tv[^"]+)"', r'window\.location\s*=\s*["\']([^"\']+bigo[^"\']+)["\']', r'URL=([^"\'>]+bigo\.tv[^"\'<>]+)']
   for pat in pats:
    m=re.search(pat, txt, re.I)
    if m:
     found=m.group(1) if m.lastindex else m.group(0)
     log+=f"เจอใน HTML: {found[:150]}\n"
     return found, log
  except Exception as e:
   log+=f"slink err {e}\n"
 return url, log

def extract_hls_from_sid_page(sid_url):
 log=""
 try:
  r=requests.get(sid_url, headers=HEADERS, timeout=15)
  log+=f"GET sid page {r.status_code} len {len(r.text)}\n"
  txt=r.text
  # Find all m3u8
  m3us=re.findall(r'https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*', txt)
  if m3us:
   # clean escaped
   cleaned=[]
   for u in m3us:
    u=u.replace('\\u002F','/').replace('\\/','/').replace('\\','')
    cleaned.append(u)
   uniq=list(dict.fromkeys(cleaned))
   log+=f"เจอ {len(uniq)} m3u8 ในหน้า:\n"+"\n".join(uniq[:5])+"\n"
   # pick best (usually contains alicdn or bigo)
   for u in uniq:
    if "bigo" in u or "alicdn" in u or "live" in u:
     return u, log
   return uniq[0], log
  # try to find in json blobs
  # look for hls url encoded
  m=re.search(r'"hls"\s*:\s*"([^"]+)"', txt)
  if m:
   u=m.group(1).replace('\\/','/')
   log+=f"เจอ hls field: {u}\n"
   return u, log
  log+=f"ไม่เจอ m3u8 ในหน้า preview: {txt[:1000]}\n"
 except Exception as e:
  log+=f"sid page err {e}\n"
 return None, log

def get_bigo_hls_api(site_id):
 urls=[f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}", f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}"]
 logs=""
 for api_url in urls:
  try:
   r=requests.get(api_url, headers=HEADERS, timeout=10)
   logs+=f"API {api_url} {r.status_code}\n"
   if r.status_code==200:
    m=re.search(r"https?://[^\s\"']+\.m3u8[^\s\"']*", r.text)
    if m:
     return m.group(0), logs
  except Exception as e:
   logs+=f"API err {e}\n"
 return None, logs

@app.route("/")
def home(): return HTML_PAGE
@app.route("/api/start", methods=["POST"])
def api_start():
 data=request.json
 raw=data.get("url","")
 m=re.search(r"https?://[^\s]+", raw)
 raw_url=m.group(0).replace(')','').strip() if m else raw
 quality=data.get("quality","best")
 job_id=uuid.uuid4().hex[:8]
 resolved, slink_log = resolve_slink(raw_url)
 cleaned = resolved.split("?")[0]+"?"+resolved.split("?")[1] if "?" in resolved else resolved  # keep query for sid
 # keep full for ffmpeg, but for siteId extract
 mm=re.search(r"/sid/(\d+)_", cleaned)
 if not mm: mm=re.search(r"bigo\.tv/(\d+)", cleaned)
 site_id=mm.group(1) if mm else "unknown"
 out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
 jobs[job_id]={"id":job_id,"url":raw_url,"resolved":cleaned,"siteid":site_id,"quality":quality,"status":"starting","log":slink_log,"time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}
 def run():
  try:
   jobs[job_id]["status"]="recording"
   log=slink_log+f"\nResolved: {cleaned[:200]}\nSiteID: {site_id}\n"
   hls=None
   if site_id!="unknown":
    # Try sid page first - most reliable
    hls1, log1 = extract_hls_from_sid_page(cleaned)
    log+=log1
    if hls1:
     hls=hls1
    else:
     hls2, log2 = get_bigo_hls_api(site_id)
     log+=log2
     if hls2:
      hls=hls2
   if hls:
    hls=hls.replace('\\u002F','/').replace('\\/','/')
    log+=f"\n>>> เจอ HLS สดแล้ว! เริ่มอัด <<<\n{hls[:200]}\n"
    jobs[job_id]["log"]=log
    cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy",out]
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
     jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-8000:]
    proc.wait()
    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
    return
   else:
    log+="\nไม่เจอ HLS จากหน้าโดยตรง ลอง yt-dlp fallback\n"
    q_map={"best":"best","1080p":"best[height<=1080]","720p":"best[height<=720]","480p SD":"best[height<=480]"}
    fmt=q_map.get(quality,"best")
    cmd=["yt-dlp","--no-check-certificate","--no-playlist","-f",fmt,"-o",out,"--merge-output-format","mp4",cleaned]
    jobs[job_id]["log"]=log+f"CMD {cmd}\n"
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
     jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-8000:]
    proc.wait()
    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
  except Exception as e:
   jobs[job_id]["log"]+=str(e)
   jobs[job_id]["status"]="error"
 threading.Thread(target=run, daemon=True).start()
 return jsonify({"id":job_id,"resolved":cleaned,"siteid":site_id,"hls":False,"raw":raw_url})
@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])

if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
