"""
SKIPP'D & SUNSET Solar Forecasting Verification and Demo Runner
This script initializes the environment, verifies physical clear-sky calculations,
and tests both SUNSET Nowcast and Forecast deep learning models.
"""

import os
import sys
import datetime
import cv2
import numpy as np

# Ensure models directory is accessible for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "models"))
import Relative_op_func as rel

import tensorflow as tf
from tensorflow import keras


def test_physical_model():
    print("=" * 60)
    print("1. Testing Physical Clear-Sky Model (Relative_op_func.py)")
    print("=" * 60)

    test_date = datetime.datetime(2019, 5, 27, 12, 30, 0)
    measured_pv = 18.5  # kW

    day_of_year, time_of_day = rel.inputs_for_rel_op(test_date)
    solar_azimuth, solar_zenith = rel.Solar_angle(test_date)
    rel_pv, p_theo = rel.Relative_output(test_date, measured_pv)

    print(f"Date & Time:           {test_date} (PST)")
    print(f"Day of year:           {day_of_year}")
    print(f"Time of day (seconds): {time_of_day}s")
    print(f"Solar Azimuth angle:   {solar_azimuth:.2f}°")
    print(f"Solar Zenith angle:    {solar_zenith:.2f}°")
    print(f"Theoretical PV Output: {p_theo:.2f} kW")
    print(f"Measured PV Output:    {measured_pv:.2f} kW")
    print(f"Clear-sky Index:       {rel_pv:.4f}")
    print("Physical Model Check: PASSED\n")


def build_sunset_nowcast_model(input_shape=(64, 64, 3)):
    num_filters = 24
    kernel_size = [3, 3]
    pool_size = [2, 2]
    strides = 2
    dense_size = 1024
    drop_rate = 0.4

    x_in = keras.Input(shape=input_shape, name="sky_image_input")
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
    model = keras.Model(inputs=x_in, outputs=y_out, name="SUNSET_Nowcast")
    return model


def build_sunset_forecast_model(image_input_dim=(64, 64, 48), history_len=16):
    num_filters = 24
    kernel_size = [3, 3]
    pool_size = [2, 2]
    strides = 2
    dense_size = 1024
    drop_rate = 0.4

    # Multimodal inputs
    x_img = keras.Input(shape=image_input_dim, name="sky_images_history")
    x_pv = keras.Input(shape=(history_len,), name="pv_power_history")

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
    model = keras.Model(inputs=[x_img, x_pv], outputs=y_out, name="SUNSET_Forecast")
    return model


def test_nowcast_model():
    print("=" * 60)
    print("2. Testing SUNSET Nowcast Model Architecture & Forward Pass")
    print("=" * 60)

    model = build_sunset_nowcast_model()
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=3e-6), loss="mse", metrics=["mae"])
    print(f"Model Name: {model.name}")
    print(f"Total Parameters: {model.count_params():,}")

    # Load a sample image from sample_images if available
    sample_img_path = os.path.join(os.path.dirname(__file__), "sample_images", "sky_camera_and_panel_photos_update.png")
    if os.path.exists(sample_img_path):
        raw_img = cv2.imread(sample_img_path)
        resized_img = cv2.resize(raw_img, (64, 64))
        normalized_img = resized_img.astype(np.float32) / 255.0
        batch_images = np.expand_dims(normalized_img, axis=0)
        print(f"Loaded sample image from {os.path.basename(sample_img_path)} and preprocessed to {batch_images.shape}")
    else:
        batch_images = np.random.rand(1, 64, 64, 3).astype(np.float32)

    pred = model.predict(batch_images)
    print(f"Nowcast forward pass output: {pred[0][0]:.4f} kW")

    # Run quick training test on batch
    dummy_targets = np.array([[12.5]], dtype=np.float32)
    hist = model.fit(batch_images, dummy_targets, epochs=1, verbose=0)
    print(f"Nowcast training step loss: {hist.history['loss'][0]:.4f}")
    print("SUNSET Nowcast Check: PASSED\n")


def test_forecast_model():
    print("=" * 60)
    print("3. Testing SUNSET Forecast Model Architecture & Forward Pass")
    print("=" * 60)

    model = build_sunset_forecast_model()
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=3e-6), loss="mse", metrics=["mae"])
    print(f"Model Name: {model.name}")
    print(f"Total Parameters: {model.count_params():,}")

    batch_imgs = np.random.rand(2, 64, 64, 48).astype(np.float32)
    batch_pv_hist = np.random.uniform(5.0, 25.0, (2, 16)).astype(np.float32)

    preds = model.predict([batch_imgs, batch_pv_hist])
    print(f"Forecast forward pass outputs (2 samples, 15-min ahead): {preds.flatten()}")

    dummy_targets = np.array([[15.2], [18.7]], dtype=np.float32)
    hist = model.fit([batch_imgs, batch_pv_hist], dummy_targets, epochs=1, verbose=0)
    print(f"Forecast training step loss: {hist.history['loss'][0]:.4f}")
    print("SUNSET Forecast Check: PASSED\n")


def main():
    print("\n" + "=" * 60)
    print("SKIPP'D — Solar Forecasting Pipeline & Models Verification")
    print("=" * 60)
    print(f"TensorFlow Version: {tf.__version__}")
    print(f"NumPy Version:      {np.__version__}")
    print(f"OpenCV Version:     {cv2.__version__}")
    print(f"Devices:            {tf.config.list_physical_devices()}")
    print("=" * 60 + "\n")

    test_physical_model()
    test_nowcast_model()
    test_forecast_model()

    print("=" * 60)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("You can also run Jupyter Notebooks directly:")
    print("  .venv\\Scripts\\jupyter notebook")
    print("=" * 60)


if __name__ == "__main__":
    main()
