import os, re, subprocess, threading, uuid, requests, json, time
from flask import Flask, request, jsonify
from datetime import datetime
app=Flask(__name__)
RECORD_DIR="/tmp/recordings"
os.makedirs(RECORD_DIR, exist_ok=True)
jobs={}
HTML_PAGE = """
<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>BIGO V14 TOKEN</title>
<style>body{background:#111;color:#fff;font-family:system-ui;padding:20px}input,select,button{width:100%;padding:14px;margin:8px 0;border-radius:12px;border:none;font-size:16px}button{background:#f59e0b;color:#000;font-weight:bold}.card{background:#1e1e1e;border-radius:16px;padding:14px;margin:12px 0;border-left:4px solid #f59e0b}pre{background:#000;padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap;font-size:11px;max-height:700px}.ok{color:#22c55e}</style>
</head><body>
<h2>BIGO V14 <span style="background:#f59e0b;color:#000;padding:4px 10px;border-radius:20px;font-size:12px">TOKEN FIX</span></h2>
<p style="color:#aaa">ส่ง b,h,mk + Cookie แบบครบ - แก้ IP Block</p>
<input id="url" placeholder="วาง slink.bigovideo.tv"><select id="q"><option>best</option><option>1080p</option><option>720p</option><option>480p SD</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="status" class="ok"></div><div id="list"></div>
<script>
function extractUrl(t){let m=t.match(/https?:\/\/[^\s]+/);if(m) return m[0].replace(/[)"'】。]+$/, '');return t.trim();}
async function start(){let raw=document.getElementById('url').value;if(!raw){alert('วางลิงก์ก่อน');return;}let url=extractUrl(raw);document.getElementById('status').innerHTML='กำลังแกะ... '+url;let q=document.getElementById('q').value;let r=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,quality:q})});let j=await r.json();document.getElementById('status').innerHTML='OK ID '+j.id+' SiteID:'+j.siteid;load();}
async function load(){let r=await fetch('/api/list');let j=await r.json();let h='';j.forEach(it=>{h+='<div class="card"><b>'+it.resolved.slice(0,100)+'</b> <small style=float:right>'+it.status+'</small><br><small>'+it.time+' Site:'+it.siteid+'</small><pre>'+(it.log||'')+'</pre></div>';});document.getElementById('list').innerHTML=h;}
setInterval(load,3000);load();
</script></body></html>
"""
HEADERS={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1","Referer":"https://www.bigo.tv/","Origin":"https://www.bigo.tv","Accept":"*/*","Accept-Language":"en-US,en;q=0.9"}

def resolve_slink(url):
 sess=requests.Session()
 log=""
 try:
  r=sess.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
  log+=f"slink {r.status_code} final:{r.url[:150]}\ncookies:{dict(sess.cookies)}\\n"
  if "bigo.tv/sid/" in r.url:
   return r.url, log, sess
  m=re.search(r'https://www\.bigo\.tv/sid/[^\s"\'<>]+', r.text)
  if m:
   return m.group(0), log+f"found in html {m.group(0)[:150]}\n", sess
 except Exception as e:
  log+=f"err {e}\n"
 return url, log, sess

def get_hls_with_token(sid_url, sess):
 log=""
 try:
  # extract tokens from URL
  site=re.search(r'/sid/(\d+)_', sid_url)
  site_id=site.group(1) if site else ""
  b=re.search(r'[?&]b=(\d+)', sid_url)
  h=re.search(r'[?&]h=(\d+)', sid_url)
  mk=re.search(r'[?&]mk=([^&]+)', sid_url)
  b_val=b.group(1) if b else ""
  h_val=h.group(1) if h else ""
  mk_val=mk.group(0) if mk else ""
  log+=f"Tokens site={site_id} b={b_val} h={h_val} {mk_val[:80]}\n"
  
  # 1. GET sid page to get more cookies
  r=sess.get(sid_url, headers=HEADERS, timeout=15)
  log+=f"GET sid {r.status_code} len {len(r.text)} cookies {dict(sess.cookies)}\n"
  txt=r.text
  
  # 2. Try to find m3u8 in sid page with all methods
  txt_clean=txt.replace('\\/','/').replace('\\u002F','/').replace('\\u002f','/')
  m3us=re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', txt_clean)
  if m3us:
   uniq=list(dict.fromkeys(m3us))
   log+=f"FOUND {len(uniq)} m3u8 in page:\n"+"\n".join(uniq[:10])+"\n"
   return uniq[0], log
  
  # 3. Try APIs with tokens
  apis=[
   f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b_val}&h={h_val}",
   f"https://www.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}",
   f"https://ta.bigo.tv/official_website/studio/getInternalStudioInfo?siteId={site_id}&b={b_val}&h={h_val}",
   f"https://www.bigo.tv/api/v2/bigo/getLiveStreamInfo?siteId={site_id}&b={b_val}&h={h_val}",
   f"https://www.bigo.tv/official_website/studio/getStudioInfo?siteId={site_id}",
   f"https://www.bigo.tv/official_website/studio/getOtherStudioInfo?siteId={site_id}&b={b_val}&h={h_val}",
   f"https://www.bigo.tv/live/api/getLiveInfo?siteId={site_id}",
  ]
  for api in apis:
   try:
    rr=sess.get(api, headers=HEADERS, timeout=10)
    body=rr.text
    log+=f"\nAPI {api}\n-> {rr.status_code} len {len(body)}\nbody preview: {body[:2000]}\n---\n"
    # search m3u8
    m=re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', body)
    if m:
     return m.group(0), log
    # try json path
    try:
     j=json.loads(body)
     # deep find
     def find(o):
      if isinstance(o,str) and ".m3u8" in o:
       return o
      if isinstance(o,dict):
       for v in o.values():
        r=find(v)
        if r: return r
      if isinstance(o,list):
       for v in o:
        r=find(v)
        if r: return r
      return None
     f=find(j)
     if f:
      return f, log+f"\nfound in json deep\n"
     # also check if data has flv or rtmp
     if "data" in j and isinstance(j["data"], dict):
      for k in ["hls","live_url","video_url","flv","rtmp","play_url","url","alive_url","http_flv_url"]:
       if k in j["data"] and isinstance(j["data"][k], str) and ("m3u8" in j["data"][k] or "flv" in j["data"][k] or "rtmp" in j["data"][k]):
        return j["data"][k], log+f"\nfound {k} in data\n"
    except:
     pass
   except Exception as e:
    log+=f"API err {api} {e}\n"
  
  # 4. Last resort - try to extract from window data
  # search for "live" json
  for key in ["liveStream","studioInfo","videoUrl","playUrl"]:
   idx=txt.find(key)
   if idx!=-1:
    snippet=txt[idx:idx+10000]
    m=re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', snippet)
    if m:
     log+=f"found in {key}\n"
     return m.group(0), log
  
  log+=f"\nNO HLS FOUND - full page snippet 0-1000:\n{txt[:1000]}\n"
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
   log=slog+f"\nResolved: {resolved}\n"
   hls, dlog = get_hls_with_token(resolved, sess)
   log+=dlog
   if hls:
    hls=hls.replace('\\/','/').split('"')[0].split("'")[0].split('<')[0]
    log+=f"\n>>> FOUND HLS <<<\n{hls[:500]}\n"
    jobs[job_id]["log"]=log
    cmd=["ffmpeg","-y","-user_agent",HEADERS["User-Agent"],"-referer","https://www.bigo.tv/","-i",hls,"-c","copy",out]
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
     jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-10000:]
    proc.wait()
    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
    return
   else:
    log+="\nNO HLS after all methods, try yt-dlp with cookies\n"
    # Build cookie header
    cookie_str="; ".join([f"{k}={v}" for k,v in sess.cookies.items()])
    cmd=["yt-dlp","--verbose","--no-check-certificate","-f","best","-o",out,"--add-header",f"Cookie: {cookie_str}","--add-header",f"Referer: https://www.bigo.tv/","--add-header",f"User-Agent: {HEADERS['User-Agent']}",resolved]
    jobs[job_id]["log"]=log+f"\nCMD: {' '.join(cmd[:10])}\n"
    proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
     jobs[job_id]["log"]=(jobs[job_id]["log"]+line)[-10000:]
    proc.wait()
    jobs[job_id]["status"]="done" if proc.returncode==0 else "error"
  except Exception as e:
   jobs[job_id]["log"]+=f"\nEXC {e}\n"
   jobs[job_id]["status"]="error"
 threading.Thread(target=run, daemon=True).start()
 return jsonify({"id":job_id,"resolved":resolved,"siteid":site_id})
@app.route("/api/list")
def api_list(): return jsonify(list(jobs.values())[::-1])
if __name__=="__main__": app.run(host="0.0.0.0", port=5000)
