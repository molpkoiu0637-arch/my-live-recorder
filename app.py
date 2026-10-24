"""
Real Private Live Recorder - FINAL VERSION for Cloud Deploy
แก้ไขให้ทำงานบน Render/Railway ได้จริง
"""
from flask import Flask, request, jsonify, send_from_directory, render_template_string
import os, uuid, threading, subprocess, json
from datetime import datetime

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

jobs = {}

HTML = """
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>My Private Live Recorder - REAL CLOUD</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-black text-white min-h-screen p-4">
<div class="max-w-md mx-auto pb-20">
<div class="flex items-center justify-between mt-2">
<h1 class="text-xl font-bold">🔴 REAL CLOUD <span class="text-[10px] bg-green-500 text-black px-2 py-1 rounded-full ml-1">ของจริง • ใช้งานได้</span></h1>
<div class="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
</div>
<p class="text-gray-400 text-xs mt-1">อัดยาวไม่จำกัด • ทุกคุณภาพฟรี • เปิดจากมือถือได้</p>

<div class="bg-zinc-900 rounded-2xl p-4 mt-5 border border-zinc-800">
<input id="url" placeholder="วางลิงก์ TikTok / YouTube / Shopee / Twitch / Douyin" class="w-full bg-zinc-800 rounded-xl p-4 text-sm outline-none focus:ring-2 focus:ring-violet-600">
<div class="grid grid-cols-2 gap-2 mt-3">
<select id="quality" class="bg-zinc-800 rounded-xl p-3 text-sm">
<option value="best">Best (สูงสุด)</option>
<option value="1080">1080p FHD</option>
<option value="720">720p HD</option>
<option value="480">480p SD</option>
</select>
<select id="mode" class="bg-zinc-800 rounded-xl p-3 text-sm">
<option value="live">ไลฟ์สด (บันทึกตอนนี้)</option>
<option value="video">วิดีโอที่ลงแล้ว</option>
</select>
</div>
<button onclick="startRecord()" id="btn" class="w-full bg-gradient-to-r from-violet-600 to-fuchsia-500 rounded-xl p-4 mt-3 font-bold text-base shadow-lg shadow-violet-900/30">เริ่มบันทึกทันที</button>
<div id="status" class="text-sm text-violet-300 mt-3 hidden p-3 bg-violet-950/30 rounded-xl"></div>
</div>

<h2 class="font-bold mt-7 mb-3 flex items-center gap-2"><span class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>กำลังบันทึก (<span id="count">0</span>)</h2>
<div id="jobs" class="space-y-3"></div>

<div class="mt-8 p-4 bg-yellow-950/30 border border-yellow-800/50 rounded-2xl text-xs text-yellow-200/80">
<b class="text-yellow-300">⚠️ ใช้งานอย่างถูกต้อง:</b> ใช้บันทึกเฉพาะไลฟ์ของตัวเองหรือได้รับอนุญาตเท่านั้น การบันทึกไลฟ์ผู้อื่นโดยไม่ได้รับอนุญาตอาจผิดข้อกำหนดแพลตฟอร์ม
</div>
</div>

<script>
async function startRecord(){
 const url = document.getElementById('url').value.trim();
 if(!url){ alert('วางลิงก์ก่อนครับ'); return; }
 const quality = document.getElementById('quality').value;
 const btn = document.getElementById('btn');
 btn.disabled = true;
 btn.innerText = 'กำลังเริ่ม...';
 try {
  const res = await fetch('/record', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, quality})});
  const data = await res.json();
  const st = document.getElementById('status');
  st.classList.remove('hidden');
  st.innerText = data.message;
  document.getElementById('url').value = '';
  loadJobs();
 } catch(e){ alert('Error: '+e); }
 btn.disabled = false;
 btn.innerText = 'เริ่มบันทึกทันที';
}

async function loadJobs(){
 try {
  const res = await fetch('/jobs');
  const jobs = await res.json();
  document.getElementById('count').innerText = jobs.filter(j=>j.status=='recording').length;
  document.getElementById('jobs').innerHTML = jobs.map(j=>`
    <div class="bg-zinc-900 rounded-2xl p-4 border border-zinc-800">
      <div class="flex justify-between items-start gap-2">
        <div class="text-sm truncate w-3/4 text-gray-200">${j.url}</div>
        <span class="text-[10px] px-2 py-1 rounded-full shrink-0 ${j.status=='recording'?'bg-red-500/20 text-red-400 border border-red-500/30':j.status=='done'?'bg-green-500/20 text-green-400 border border-green-500/30':'bg-zinc-700 text-gray-300'}">${j.status=='recording'?'● กำลังอัด':j.status=='done'?'✓ เสร็จแล้ว':j.status}</span>
      </div>
      <div class="text-[11px] text-gray-500 mt-1">${j.started} • ${j.quality} • ID:${j.id}</div>
      ${j.file?`<a href="/download/${j.file}" class="block mt-3 bg-white text-black text-center rounded-xl p-3 text-sm font-bold">⬇️ ดาวน์โหลดไฟล์</a>`:''}
      <div class="text-[11px] text-gray-400 mt-2 font-mono bg-black/50 p-2 rounded-lg truncate">${(j.log||'').slice(-200)}</div>
    </div>
  `).join('') || '<div class="text-center text-gray-600 text-sm py-10">ยังไม่มีงานบันทึก วางลิงก์ด้านบนได้เลย</div>';
 } catch(e){}
}
setInterval(loadJobs, 2500);
loadJobs();
</script>
</body>
</html>
"""

def run_yt_dlp(job_id, url, quality):
    job = jobs[job_id]
    filename = f"{job_id}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    
    if quality == "best":
        fmt = "bestvideo+bestaudio/best"
    else:
        fmt = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"

    if ".m3u8" in url:
        cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", filepath]
    else:
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", fmt,
            "-o", filepath,
            "--merge-output-format", "mp4",
            "--no-warnings",
            "--live-from-start",
            url
        ]

    try:
        job["log"] = f"เริ่ม: {' '.join(cmd)[:150]}"
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            job["log"] = line.strip()[-400:]
        proc.wait()
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            job["status"] = "done"
            job["file"] = filename
            size_mb = os.path.getsize(filepath)//1024//1024
            job["log"] = f"✅ เสร็จแล้ว {size_mb} MB - กดดาวน์โหลดได้เลย"
        else:
            job["status"] = "error"
            job["log"] = "❌ ลิงก์ไม่รองรับ หรือไลฟ์จบแล้ว ลองเช็คลิงก์อีกที"
    except Exception as e:
        job["status"] = "error"
        job["log"] = f"Error: {str(e)[:300]}"

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/record", methods=["POST"])
def record():
    data = request.get_json()
    url = data.get("url","").strip()
    quality = data.get("quality","best")
    if not url:
        return jsonify({"message": "กรุณาวางลิงก์"}), 400
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {
        "id": job_id, "url": url, "quality": quality,
        "status": "recording",
        "started": datetime.now().strftime("%H:%M:%S %d/%m"),
        "file": None, "log": "กำลังเชื่อมต่อ..."
    }
    threading.Thread(target=run_yt_dlp, args=(job_id, url, quality), daemon=True).start()
    return jsonify({"message": f"✅ เริ่มอัดแล้ว! ID {job_id} - เลื่อนลงดูสถานะ", "job_id": job_id})

@app.route("/jobs")
def get_jobs():
    return jsonify(list(jobs.values())[::-1])

@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

# สำหรับ gunicorn
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
