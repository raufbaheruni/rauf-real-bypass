import cv2
import numpy as np
import os
import io
import tempfile
from datetime import datetime
from PIL import Image
from flask import Flask, render_template, request, send_file

try:
    import piexif
except ImportError:
    os.system("pip install piexif")
    import piexif

app = Flask(__name__)

def real_camera_bypass(file_bytes):
    pil_img = Image.open(io.BytesIO(file_bytes))
    if pil_img.mode in ("RGBA", "P"):
        pil_img = pil_img.convert("RGB")
    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    max_size = 1500
    h, w = img.shape[:2]
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    if img.shape[0] > 10 and img.shape[1] > 10:
        img = img[2:-2, 2:-2]

    h, w = img.shape[:2]

    # ATTACK 1: GEOMETRIC WARP (1 डिग्री घुमाना)
    M = cv2.getRotationMatrix2D((w/2, h/2), 1.0, 1.0)
    img_rot = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    cy, cx = int(h*0.02), int(w*0.02)
    img_crop = img_rot[cy:h-cy, cx:w-cx]
    h, w = img_crop.shape[:2]

    # ATTACK 2: CHROMATIC ABERRATION (हल्का कलर शिफ्ट)
    b, g, r = cv2.split(img_crop)
    r_shifted = np.roll(r, 1, axis=1)
    b_shifted = np.roll(b, -1, axis=1)
    img_ca = cv2.merge((b_shifted, g, r_shifted))

    # ATTACK 3: SIGNAL-DEPENDENT SENSOR NOISE (Brightness Fix)
    ycrcb = cv2.cvtColor(img_ca, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)

    y_float = y.astype(np.float32) / 255.0
    noise_scale = 1.0 + y_float * 3.0
    noise_y = np.random.normal(0, 1.0, y.shape) * noise_scale
    y_att = np.clip(y.astype(np.float32) + noise_y, 0, 255).astype(np.uint8)

    cr_blur = cv2.GaussianBlur(cr, (3, 3), 0)
    cb_blur = cv2.GaussianBlur(cb, (3, 3), 0)
    cr_att = np.clip(cr_blur.astype(np.float32) + np.random.normal(0, 1.0, cr.shape), 0, 255).astype(np.uint8)
    cb_att = np.clip(cb_blur.astype(np.float32) + np.random.normal(0, 1.0, cb.shape), 0, 255).astype(np.uint8)

    ycrcb_att = cv2.merge((y_att, cr_att, cb_att))
    img_color_attack = cv2.cvtColor(ycrcb_att, cv2.COLOR_YCrCb2BGR)

    # ATTACK 4: LIGHT JPEG GHOST (Quality Fix - 75%)
    _, enc_img = cv2.imencode('.jpg', img_color_attack, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    img_ghost = cv2.imdecode(enc_img, 1)

    # HD RECOVERY (हल्की शार्पनिंग)
    gaussian = cv2.GaussianBlur(img_ghost, (0, 0), sigmaX=0.5)
    img_sharp = cv2.addWeighted(img_ghost.astype(np.float32), 1.2, gaussian.astype(np.float32), -0.2, 0)
    final_img = np.clip(img_sharp, 0, 255).astype(np.uint8)

    # EXIF METADATA (iPhone 16 Pro)
    now = datetime.now().strftime("%Y:%m:%d %H:%M:%S")
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Apple",
            piexif.ImageIFD.Model: b"iPhone 16 Pro",
            piexif.ImageIFD.Software: b"17.4.1",
            piexif.ImageIFD.DateTime: now.encode('utf-8'),
            piexif.ImageIFD.XResolution: (72, 1),
            piexif.ImageIFD.YResolution: (72, 1),
            piexif.ImageIFD.ResolutionUnit: 2
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: now.encode('utf-8'),
            piexif.ExifIFD.DateTimeDigitized: now.encode('utf-8'),
            piexif.ExifIFD.LensModel: b"iPhone 16 Pro back triple camera 24mm f/1.78",
            piexif.ExifIFD.LensMake: b"Apple",
            piexif.ExifIFD.ExposureTime: (1, 120),
            piexif.ExifIFD.FNumber: (18, 10),
            piexif.ExifIFD.ISOSpeedRatings: 64,
            piexif.ExifIFD.PixelXDimension: w,
            piexif.ExifIFD.PixelYDimension: h
        }
    }
    exif_bytes = piexif.dump(exif_dict)

    img_rgb = cv2.cvtColor(final_img, cv2.COLOR_BGR2RGB)
    pil_final_img = Image.fromarray(img_rgb)

    temp_dir = tempfile.gettempdir()
    out_path = os.path.join(temp_dir, "BAHERUNI.jpg")
    pil_final_img.save(out_path, "JPEG", quality=98, subsampling=2, exif=exif_bytes)
    
    return out_path

@app.route('/profile.jpg')
def profile_pic():
    return send_file('profile.jpg', mimetype='image/jpeg')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return "No file uploaded", 400
    file = request.files['file']
    if file.filename == '':
        return "No file selected", 400
    
    try:
        file_bytes = file.read()
        output_path = real_camera_bypass(file_bytes)
        return send_file(output_path, as_attachment=True, download_name='BAHERUNI.jpg')
    except Exception as e:
        import traceback
        return traceback.format_exc(), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
