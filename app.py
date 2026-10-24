
import os, re, uuid, subprocess, threading, time, requests
from flask import Flask, request, jsonify, render_template_string, send_from_directory

app = Flask(__name__)
DOWNLOAD_DIR = "/tmp/recordings"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
jobs = {}

TEMPLATE = """
<!DOCTYPE html><html lang="th"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>REAL CLOUD V3 - YouTube Fixed</title>
<style>
body{background:#0a0a0a;color:#fff;font-family:sans-serif;padding:12px}
.card{background:#1a1a1a;border-radius:16px;padding:16px;margin-bottom:12px}
input,select{width:100%;background:#222;color:#fff;border:1px solid #333;border-radius:12px;padding:14px;font-size:16px;margin-bottom:10px;box-sizing:border-box}
button{background:linear-gradient(90deg,#8a2be2,#ff00ff);color:#fff;border:none;border-radius:12px;padding:16px;width:100%;font-size:18px;font-weight:bold}
.job{background:#1a1a1a;border-radius:12px;padding:12px;margin-top:10px;border-left:4px solid #333;word-break:break-all}
.job.ok{border-color:#0f0}.job.error{border-color:#f00}.job.run{border-color:#ff0}
small{color:#888}
pre{white-space:pre-wrap;font-size:11px;background:#000;padding:8px;border-radius:8px;max-height:200px;overflow:auto}
</style></head>
<body>
<h2>🔴 REAL CLOUD <span style="background:#0f0;color:#000;font-size:12px;padding:4px 8px;border-radius:8px">V3 YouTube Fixed</span></h2>
<p style="color:#888">อัดยาวไม่จำกัด • แก้ YouTube / Bigo แล้ว</p>
<div class="card">
<input id="url" placeholder="วางลิงก์ YouTube / Bigo ID / TikTok">
<select id="q"><option>480p SD</option><option selected>720p HD</option><option>1080p FHD</option><option>best</option></select>
<button onclick="start()">เริ่มบันทึกทันที</button>
<div id="msg" style="margin-top:10px"></div>
</div>
<div id="list"></div>
<script>
async function start(){
 let u=document.getElementById('url').value.trim();
 if(!u){alert('ใส่ลิงก์ก่อน');return}
 document.getElementById('msg').innerHTML='⏳ กำลังเริ่ม...';
 let r=await fetch('/api/record',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u,quality:document.getElementById('q').value})});
 let j=await r.json();
 document.getElementById('msg').innerHTML = r.ok ? '✅ เริ่มแล้ว ID '+j.id : '❌ '+j.error;
 load();
}
async function load(){
 let r=await fetch('/api/jobs'); let j=await r.json();
 let h=''; let c=0;
 for(let id in j){
  let x=j[id]; if(x.status=='recording') c++;
  h+=`<div class="job ${x.status=='recording'?'run':x.status=='done'?'ok':'error'}">
  <b>${x.url}</b> <span style="float:right;background:#333;padding:2px 8px;border-radius:8px;font-size:12px">${x.status}</span><br>
  <small>${x.time} • ${x.quality} • ID:${id.slice(0,8)}</small>
  <pre>${x.log||''}</pre>
  ${x.file ? `<a href="/download/${id}" style="color:#0f0">⬇️ ดาวน์โหลด</a>`:''}
  </div>`;
 }
 document.getElementById('list').innerHTML='<h3>🔴 กำลังบันทึก ('+c+')</h3>'+h;
}
setInterval(load,3000); load();
</script>
</body></html>
"""

def normalize_url(raw):
    raw=raw.strip()
    if re.match(r'^\d{5,}$', raw):
        return f'https://www.bigo.tv/{raw}'
    if 'slink.bigovideo.tv' in raw or 'bigovideo.tv' in raw:
        try:
            r=requests.get(raw,allow_redirects=True,timeout=10,headers={'User-Agent':'Mozilla/5.0'})
            m=re.search(r'bigo\.tv/(\d+)', r.url)
            if m: return f'https://www.bigo.tv/{m.group(1)}'
            return r.url
        except: return raw
    if 'youtu.be/' in raw:
        # convert youtu.be/VIDEOID to youtube.com/watch?v=VIDEOID
        m=re.search(r'youtu\.be/([A-Za-z0-9_-]+)', raw)
        if m: return f'https://www.youtube.com/watch?v={m.group(1)}'
    if '/live/' in raw and 'youtube.com' in raw:
        # /live/VIDEOID -> /watch?v=VIDEOID for yt-dlp compatibility
        m=re.search(r'/live/([A-Za-z0-9_-]+)', raw)
        if m: return f'https://www.youtube.com/watch?v={m.group(1)}'
    return raw

def run_job(job_id, url, quality):
    job=jobs[job_id]
    norm=normalize_url(url)
    job['url']=norm
    job['log']=f"🔗 ใช้ลิงก์: {norm}\n⏳ กำลังเช็ค..."
    q_map={'480p SD':'480','720p HD':'720','1080p FHD':'1080','best':'best'}
    q=q_map.get(quality,'720')
    out=os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")
    # YT-DLP command optimized for YouTube bypass on cloud
    cmd=[
        "yt-dlp",
        "--no-playlist",
        "-f", f"best[height<={q}]/best" if q!='best' else "best",
        "-o", out,
        "--merge-output-format","mp4",
        "--user-agent","Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "--extractor-args","youtube:player_client=android,web;po_token=web+android",
        "--extractor-retries","5",
        "--socket-timeout","30",
        "--no-check-certificate",
        norm
    ]
    if 'bigo.tv' in norm:
        cmd.extend(["--add-header","Referer:https://www.bigo.tv/"])

    try:
        proc=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        logs=""
        for line in proc.stdout:
            logs+=line
            if len(logs)>5000: logs=logs[-5000:]
            job['log']=logs[-2000:]
            if proc.poll() is not None:
                break
        if proc.returncode==0:
            # find file
            import glob
            files=glob.glob(os.path.join(DOWNLOAD_DIR, f"{job_id}.*"))
            if files:
                job['file']=files[0]
                job['status']='done'
                job['log']=f"✅ สำเร็จ!\n{logs[-1000:]}"
            else:
                job['status']='error'
                job['log']=f"❌ เสร็จแต่หาไฟล์ไม่เจอ\n{logs[-2000:]}"
        else:
            job['status']='error'
            job['log']=f"❌ Error:\n{logs[-3000:]}"
    except Exception as e:
        job['status']='error'
        job['log']=f"Exception: {e}"

@app.route('/')
def index(): return render_template_string(TEMPLATE)

@app.route('/api/record', methods=['POST'])
def api_record():
    data=request.json
    url=data.get('url','').strip()
    if not url: return jsonify({'error':'ใส่ลิงก์ก่อน'}),400
    jid=uuid.uuid4().hex[:12]
    jobs[jid]={'url':url,'quality':data.get('quality','720p HD'),'status':'recording','time':time.strftime("%H:%M:%S %d/%m"),'log':'เริ่มแล้ว...','file':None}
    threading.Thread(target=run_job, args=(jid, url, data.get('quality','720p HD')), daemon=True).start()
    return jsonify({'id':jid})

@app.route('/api/jobs')
def api_jobs(): return jsonify(jobs)

@app.route('/download/<jid>')
def download(jid):
    j=jobs.get(jid)
    if not j or not j.get('file') or not os.path.exists(j['file']): return "File not found",404
    return send_from_directory(DOWNLOAD_DIR, os.path.basename(j['file']), as_attachment=True)

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))
