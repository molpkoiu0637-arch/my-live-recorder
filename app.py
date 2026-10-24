import os, re, subprocess, threading, uuid, requests
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
RECORD_DIR="/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs={}
HTML_PAGE = '''
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V13 FINAL</title>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:20px}input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}button{background:#a855f7;color:#fff;font-weight:bold}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #a855f7}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:12px;max-height:600px}.ok{color:#22c55e}</style>
</head><body>
<h2>BIGO V13 <span style="background:#a855f7;padding:4px 10px;border-radius:20px;font-size:12px">DEEP SCAN</span></h2>
<input id="url" placeholder="วาง slink.bigovideo.tv"><select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="status" class="ok"></div><div id="list"></div>
<script>
function extractUrl(t){let m=t.match(/https?:\/\/[^\s]+/);if(m) return m[0].replace(/[)"'】。]+$/, '');return t.trim();}
async function start(){let raw=document.getElementById('url').value;if(!raw){alert('วางลิงก์ก่อน');return;}let url=extractUrl(raw);document.getElementById('status').innerHTML='กำลังแกะ... '+url;let q=document.getElementById('q').value;let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,quality:q})});let j=await r.json();document.getElementById('status').innerHTML='OK ID '+j.id+'<br>SiteID:'+j.siteid;load();}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{h+='<div class="card"><b>'+it.resolved.slice(0,100)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+' Site:'+it.siteid+'</small><pre>'+(it.log||'')+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
'''
HEADERS={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1","Referer":"https://www.bigo.tv/","Origin":"https://www.bigo.tv"}
def resolve_slink(url):
 log=""
 sess=requests.Session()
 try:
  r=sess.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
  log+=f"slink {r.status_code} final:{r.url[:150]}\n"
  if "bigo.tv/sid/" in r.url:
   return r.url, log, sess
  m=re.search(r'https://www\.bigo\.tv/sid/[^\s"\'<>]+', r.text)
  if m:
   return m.group(0), log+f"found in html {m.group(0)[:150]}\n", sess
 except Exception as e:
  log+=f"err {e}\n"
 return url, log, sess

def deep_extract(sid_url, sess):
 log=""
 try:
  r=sess.get(sid_url, headers=HEADERS, timeout=15)
  log+=f"GET sid {r.status_code} len {len(r.text)}\n"
  txt=r.text.replace('\\/','/').replace('\\u002F','/')
  # search m3u8
  m3us=re.findall(r'https?://[^\s"\']+\.m3u8[^\s"\']*', txt)
  if m3us:
   uniq=list(dict.fromkeys(m3us))
   log+=f"found {len(uniq)} m3u8:\n"+ "\n".join(uniq[:10])+"\n"
   return uniq[0], log
  # search in script tags json
  for pat in [r'"hls"\s*:\s*"([^"]+)"', r'"videoSrc"\s*:\s*"([^"]+)"', r'"src"\s*:\s*"(https[^"]+m3u8[^"]+)"']:
   m=re.search(pat, txt)
   if m:
    return m.group(1).replace('\\/','/'), log+f"found via {pat}\n"
  # try APIs
  site=re.search(r'/sid/(\d+)_', sid_url)
  sid=site.group(1) if site else ""
  apis=[f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={sid}", f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={sid}", f"https://www.bigo.tv/official_website/studio/getStudioInfo?siteId={sid}"]
  for api in apis:
   try:
    rr=sess.get(api, headers=HEADERS, timeout=10)
    log+=f"API {api} {rr.status_code} {rr.text[:1000]}\n"
    m=re.search(r'https?://[^\s"\']+\.m3u8[^\s"\']*', rr.text)
    if m:
     return m.group(0), log
   except Exception as e:
    log+=f"API err {e}\n"
  log+=f"preview {txt[:800]}\n"
 except Exception as e:
  log+=f"deep err {e}\n"
 return None, log

@app.route("/")
def home(): return HTML_PAGE
@app.route("/api/start", methods=["POST"])
def api_start():
 data=request.json
 raw=data.get("url","")
 m=re.search(r"https?://[^\s]+", raw)
 raw_url=m.group(0).strip(')"\'') if m else raw
 quality=data.get("quality","best")
 job_id=uuid.uuid4().hex[:8]
 resolved, slog, sess = resolve_slink(raw_url)
 site_m=re.search(r"/sid/(\d+)_", resolved)
 site_id=site_m.group(1) if site_m else "unknown"
 out=os.path.join(RECORD_DIR, f"{job_id}.mp4")
 jobs[job_id]={"id":job_id,"url":raw_url,"resolved":resolved,"siteid":site_id,"quality":quality,"status":"starting","log":slog,"time":datetime.now().strftime("%H:%M:%S %d/%m"),"file":out}
 def run():
  try:
   jobs[job_id]["status"]="recording"
   log=slog+f"\nResolved: {resolved}\nSiteID: {site_id}\n"
   hls, dlog = deep_extract(resolved, sess)
   log+=dlog
   if hls:
    hls=hls.split('"')[0].split("'")[0]
    log+=f"\n>>> เจอ HLS <<<\n{hls[:300]}\n"
    jobs[job_id]["log"]=log
    cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy",out]
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
     jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-8000:]
    proc.wait()
    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
    return
   else:
    log+="\nไม่เจอ HLS ลอง yt-dlp\n"
    cmd=["yt-dlp","-f","best","-o",out,"--merge-output-format","mp4",resolved]
    jobs[job_id]["log"]=log
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
     jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-8000:]
    proc.wait()
    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
  except Exception as e:
   jobs[job_id]["log"]+=str(e)
   jobs[job_id]["status"]="error"
 threading.Thread(target=run, daemon=True).start()
 return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id,"raw":raw_url})
@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])
if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
