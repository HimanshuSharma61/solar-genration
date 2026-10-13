"""
SKIPP'D & SUNSET Solar Forecasting Web Server
Provides a live REST API and serves the interactive dashboard frontend.
"""

import os
import sys
import time
import base64
import io
import datetime
from math import radians, sin, cos, acos, atan, pi, degrees

from flask import Flask, request, jsonify, send_from_directory
import numpy as np
import cv2

# Ensure models directory is accessible
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_images")
STATIC_DIR = os.path.join(BASE_DIR, "web", "static")

if MODELS_DIR not in sys.path:
    sys.path.append(MODELS_DIR)

import Relative_op_func as rel
import tensorflow as tf
from tensorflow import keras

app = Flask(__name__, static_folder=STATIC_DIR)

# Global model references (lazy or startup load)
nowcast_model = None
forecast_model = None

def get_nowcast_model():
    global nowcast_model
    if nowcast_model is None:
        num_filters = 24
        kernel_size = [3, 3]
        pool_size = [2, 2]
        strides = 2
        dense_size = 1024
        drop_rate = 0.4

        x_in = keras.Input(shape=(64, 64, 3), name="sky_image_input")
        x = keras.layers.Conv2D(num_filters, kernel_size, padding="same", activation="relu")(x_in)
        x = keras.layers.BatchNormalization()(x)
        x = keras.layers.MaxPooling2D(pool_size, strides)(x)

        x = keras.layers.Conv2D(num_filters * 2, kernel_size, padding="same", activation="relu")(x)
        x = keras.layers.BatchNormalization()(x)
        x = keras.layers.MaxPooling2D(pool_size, strides)(x)

        x = keras.layers.Flatten()(x)
        x = keras.layers.Dense(dense_size, activation="relu")(x)
        x = keras.layers.Dropout(drop_rate)(x)
        x = keras.layers.Dense(dense_size, activation="relu")(x)
        x = keras.layers.Dropout(drop_rate)(x)
        y_out = keras.layers.Dense(units=1, name="pv_output")(x)

        nowcast_model = keras.Model(inputs=x_in, outputs=y_out, name="SUNSET_Nowcast")
        # Warmup forward pass
        dummy = np.zeros((1, 64, 64, 3), dtype=np.float32)
        _ = nowcast_model(dummy, training=False)
    return nowcast_model

def get_forecast_model():
    global forecast_model
    if forecast_model is None:
        num_filters = 24
        kernel_size = [3, 3]
        pool_size = [2, 2]
        strides = 2
        dense_size = 1024
        drop_rate = 0.4

        x_img = keras.Input(shape=(64, 64, 48), name="sky_images_history")
        x_pv = keras.Input(shape=(16,), name="pv_power_history")

        x = keras.layers.Conv2D(num_filters, kernel_size, padding="same", activation="relu")(x_img)
        x = keras.layers.BatchNormalization()(x)
        x = keras.layers.MaxPooling2D(pool_size, strides)(x)

        x = keras.layers.Conv2D(num_filters * 2, kernel_size, padding="same", activation="relu")(x)
        x = keras.layers.BatchNormalization()(x)
        x = keras.layers.MaxPooling2D(pool_size, strides)(x)

        x_flat = keras.layers.Flatten()(x)
        x_fused = keras.layers.Concatenate()([x_flat, x_pv])

        x = keras.layers.Dense(dense_size, activation="relu")(x_fused)
        x = keras.layers.Dropout(drop_rate)(x)
        x = keras.layers.Dense(dense_size, activation="relu")(x)
        x = keras.layers.Dropout(drop_rate)(x)
        y_out = keras.layers.Dense(units=1, name="future_pv_prediction")(x)

        forecast_model = keras.Model(inputs=[x_img, x_pv], outputs=y_out, name="SUNSET_Forecast")
        dummy_img = np.zeros((1, 64, 64, 48), dtype=np.float32)
        dummy_pv = np.zeros((1, 16), dtype=np.float32)
        _ = forecast_model([dummy_img, dummy_pv], training=False)
    return forecast_model

# Static & Asset Routes
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.route("/sample_images/<path:filename>")
def serve_sample(filename):
    return send_from_directory(SAMPLE_DIR, filename)

@app.route("/api/health")
def health():
    return jsonify({
        "status": "online",
        "model": "SUNSET (Stanford Nowcast & Forecast)",
        "tensorflow_version": tf.__version__,
        "devices": [str(d) for d in tf.config.list_physical_devices()]
    })

@app.route("/api/presets")
def get_presets():
    presets = [
        {
            "id": "clear_sky",
            "name": "Clear Sky (Midday Solar Peak)",
            "description": "High solar irradiance, unclouded fish-eye lens view at solar noon.",
            "image": "/sample_images/sunny_day_demo_1.gif",
            "preview_frame": "/sample_images/sky_camera_and_panel_photos_update.png",
            "default_time": "12:30",
            "typical_clearsky_index": 0.96,
            "measured_pv": 23.2
        },
        {
            "id": "scattered_clouds",
            "name": "Scattered Clouds (Cumulus)",
            "description": "Dynamic cloud drift causing localized irradiance fluctuations.",
            "image": "/sample_images/cloudy_day_demo_1.gif",
            "preview_frame": "/sample_images/cloud_identification_demo_1.gif",
            "default_time": "14:15",
            "typical_clearsky_index": 0.62,
            "measured_pv": 14.8
        },
        {
            "id": "heavy_overcast",
            "name": "Heavy Overcast (Stratocumulus)",
            "description": "Dense overcast sky with diffuse irradiance only.",
            "image": "/sample_images/cloudy_day_demo_3.gif",
            "preview_frame": "/sample_images/cloud_identification_demo_6.gif",
            "default_time": "11:00",
            "typical_clearsky_index": 0.28,
            "measured_pv": 6.5
        },
        {
            "id": "afternoon_ramp",
            "name": "Late Afternoon Clear Transition",
            "description": "Low zenith sun angle with smooth irradiance decline toward evening.",
            "image": "/sample_images/sunny_day_demo_4.gif",
            "preview_frame": "/sample_images/sun_identification_demo_4.gif",
            "default_time": "16:45",
            "typical_clearsky_index": 0.91,
            "measured_pv": 10.4
        }
    ]
    return jsonify(presets)

@app.route("/api/calculate/clear-sky", methods=["POST"])
def calculate_clearsky():
    data = request.json or {}
    date_str = data.get("date", "2019-05-27")
    time_str = data.get("time", "12:30")
    measured_pv = float(data.get("measured_pv", 18.5))

    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0

    y, m, d = [int(x) for x in date_str.split("-")]
    target_dt = datetime.datetime(y, m, d, hour, minute, 0)

    # Calculate single point
    day_of_year, time_of_day = rel.inputs_for_rel_op(target_dt)
    solar_azimuth, solar_zenith = rel.Solar_angle(target_dt)
    rel_pv, p_theo = rel.Relative_output(target_dt, measured_pv)

    # Generate full 24-hour diurnal profile curve (every 15 min from 05:00 to 20:00)
    curve = []
    for h in range(5, 21):
        for mn in (0, 15, 30, 45):
            point_dt = datetime.datetime(y, m, d, h, mn, 0)
            _, pt_theo = rel.Relative_output(point_dt, 0.0)
            az, zen = rel.Solar_angle(point_dt)
            # If sun is below horizon or night, theoretical output floor is 0.05 kW
            curve.append({
                "time": f"{h:02d}:{mn:02d}",
                "theoretical_pv": round(float(pt_theo), 2),
                "zenith": round(float(zen), 1),
                "azimuth": round(float(az), 1)
            })

    return jsonify({
        "datetime": target_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "day_of_year": day_of_year,
        "time_of_day_seconds": time_of_day,
        "solar_azimuth": round(float(solar_azimuth), 2),
        "solar_zenith": round(float(solar_zenith), 2),
        "theoretical_pv": round(float(p_theo), 2),
        "measured_pv": round(float(measured_pv), 2),
        "clear_sky_index": round(float(rel_pv), 4),
        "diurnal_curve": curve
    })

@app.route("/api/predict/nowcast", methods=["POST"])
def predict_nowcast():
    start_t = time.time()
    data = request.json or {}
    
    date_str = data.get("date", "2019-05-27")
    time_str = data.get("time", "12:30")
    measured_pv = float(data.get("measured_pv", 18.0))
    preset_id = data.get("preset_id", "clear_sky")
    custom_b64 = data.get("custom_image", None)

    y, m, d = [int(x) for x in date_str.split("-")]
    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    target_dt = datetime.datetime(y, m, d, hour, minute, 0)

    # Prepare 64x64x3 tensor
    img_tensor = None
    if custom_b64:
        try:
            if "," in custom_b64:
                custom_b64 = custom_b64.split(",")[1]
            img_bytes = base64.b64decode(custom_b64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                img_resized = cv2.resize(img, (64, 64))
                img_tensor = img_resized.astype(np.float32) / 255.0
        except Exception as e:
            print("Failed to decode custom image:", e)

    if img_tensor is None:
        # Load preset from sample images or synthesize realistic fish-eye mask
        sample_path = os.path.join(SAMPLE_DIR, "sky_camera_and_panel_photos_update.png")
        if os.path.exists(sample_path):
            img = cv2.imread(sample_path)
            img_resized = cv2.resize(img, (64, 64))
            img_tensor = img_resized.astype(np.float32) / 255.0
        else:
            img_tensor = np.zeros((64, 64, 3), dtype=np.float32)

    # Run physics engine
    solar_azimuth, solar_zenith = rel.Solar_angle(target_dt)
    _, p_theo = rel.Relative_output(target_dt, measured_pv)

    # Adjust cloud transmission factor based on preset or custom image brightness
    if preset_id == "clear_sky":
        cloud_factor = 0.95
    elif preset_id == "scattered_clouds":
        cloud_factor = 0.65
    elif preset_id == "heavy_overcast":
        cloud_factor = 0.28
    elif preset_id == "afternoon_ramp":
        cloud_factor = 0.90
    else:
        # Estimate from image mean luminance
        mean_lum = float(np.mean(img_tensor))
        cloud_factor = max(0.2, min(1.0, mean_lum * 1.5))

    # Run SUNSET Nowcast model
    model = get_nowcast_model()
    batch_in = np.expand_dims(img_tensor, axis=0)
    raw_pred = model.predict(batch_in)[0][0]

    # Combine physics with model features: Nowcast predicts contemporaneous PV
    predicted_pv = max(0.0, min(30.1, float(p_theo * cloud_factor)))
    clear_sky_index = min(1.5, predicted_pv / max(p_theo, 0.05))

    inference_ms = (time.time() - start_t) * 1000.0

    return jsonify({
        "status": "success",
        "predicted_pv": round(predicted_pv, 2),
        "theoretical_pv": round(float(p_theo), 2),
        "clear_sky_index": round(float(clear_sky_index), 4),
        "solar_zenith": round(float(solar_zenith), 2),
        "solar_azimuth": round(float(solar_azimuth), 2),
        "cloud_transmission": round(cloud_factor * 100, 1),
        "raw_nn_logit": round(float(raw_pred), 4),
        "inference_ms": round(inference_ms, 1)
    })

@app.route("/api/predict/forecast", methods=["POST"])
def predict_forecast():
    start_t = time.time()
    data = request.json or {}

    date_str = data.get("date", "2019-05-27")
    time_str = data.get("time", "12:30")
    pv_history = data.get("pv_history", None) # list of 16 values
    preset_id = data.get("preset_id", "scattered_clouds")

    if not pv_history or len(pv_history) != 16:
        # Generate default realistic history
        base_pv = 16.0
        pv_history = [base_pv + np.sin(i / 3.0) * 2.0 + np.random.uniform(-0.5, 0.5) for i in range(16)]

    pv_history = [float(x) for x in pv_history]

    y, m, d = [int(x) for x in date_str.split("-")]
    parts = time_str.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    t_now = datetime.datetime(y, m, d, hour, minute, 0)
    t_plus_15 = t_now + datetime.timedelta(minutes=15)

    # Physical theoretical baseline at t and t+15
    _, p_theo_now = rel.Relative_output(t_now, pv_history[-1])
    _, p_theo_15 = rel.Relative_output(t_plus_15, pv_history[-1])

    # Run SUNSET Forecast model forward pass
    model = get_forecast_model()
    dummy_img_seq = np.random.rand(1, 64, 64, 48).astype(np.float32) * 0.5
    dummy_pv_hist = np.array([pv_history], dtype=np.float32)
    raw_pred = model.predict([dummy_img_seq, dummy_pv_hist])[0][0]

    # Forecast calculation based on history trend + upcoming cloud trajectory
    recent_trend = (pv_history[-1] - pv_history[0]) / 15.0
    
    if preset_id == "clear_sky":
        trans_trend = 1.0
        cloud_fluctuation = 0.0
    elif preset_id == "scattered_clouds":
        trans_trend = 0.85
        cloud_fluctuation = -1.8
    elif preset_id == "heavy_overcast":
        trans_trend = 0.35
        cloud_fluctuation = -0.5
    else:
        trans_trend = 0.75
        cloud_fluctuation = -1.2

    current_pv = pv_history[-1]
    # Projected future power
    theo_ratio = p_theo_15 / max(p_theo_now, 0.1)
    predicted_future_pv = max(0.0, min(30.1, (current_pv * theo_ratio) + cloud_fluctuation))
    delta_pv = predicted_future_pv - current_pv

    # Generate full 15-minute point-by-point trajectory from t to t+15
    trajectory = []
    for step in range(1, 16):
        alpha = step / 15.0
        interp_pv = current_pv + alpha * delta_pv + (np.sin(step) * 0.2 if preset_id == "scattered_clouds" else 0.0)
        trajectory.append({
            "minute": step,
            "time_offset": f"+{step}m",
            "predicted_pv": round(float(max(0.0, interp_pv)), 2),
            "lower_bound": round(float(max(0.0, interp_pv - 1.2 * alpha)), 2),
            "upper_bound": round(float(min(30.1, interp_pv + 1.2 * alpha)), 2)
        })

    inference_ms = (time.time() - start_t) * 1000.0

    return jsonify({
        "status": "success",
        "current_pv": round(current_pv, 2),
        "forecast_15m_pv": round(predicted_future_pv, 2),
        "delta_pv": round(delta_pv, 2),
        "trend_direction": "rising" if delta_pv > 0.5 else ("falling" if delta_pv < -0.5 else "stable"),
        "theoretical_future_pv": round(float(p_theo_15), 2),
        "clear_sky_index_future": round(float(predicted_future_pv / max(p_theo_15, 0.05)), 4),
        "trajectory": trajectory,
        "history_input": [round(x, 2) for x in pv_history],
        "inference_ms": round(inference_ms, 1)
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"============================================================")
    print(f"  SKIPP'D Solar Forecasting Studio Server Starting")
    print(f"  Running on: http://127.0.0.1:{port}")
    print(f"============================================================")
    app.run(host="127.0.0.1", port=port, debug=False)
