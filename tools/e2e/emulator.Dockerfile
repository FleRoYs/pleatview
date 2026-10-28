# Android TV emulator for tools/e2e/run.py. Needs /dev/kvm on the host.
FROM pleatview-android-build

ARG SYSTEM_IMAGE="system-images;android-36;android-tv;x86_64"

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpulse0 libnss3 libxcomposite1 libxcursor1 libxi6 libxtst6 libasound2t64 libgl1 \
      libxdamage1 libxrandr2 libxkbfile1 libdbus-1-3 libfontconfig1 libx11-xcb1 libxkbcommon0 \
 && rm -rf /var/lib/apt/lists/*
RUN yes | sdkmanager --install "emulator" "$SYSTEM_IMAGE" > /dev/null \
 && chmod -R a+rwX "$ANDROID_HOME" \
 && echo no | avdmanager create avd -n tv -k "$SYSTEM_IMAGE" -d tv_1080p

# Create the adb key up front: the emulator trusts it from first boot, so adb never
# meets an "unauthorized" device.
RUN mkdir -p /root/.android && adb keygen /root/.android/adbkey > /dev/null

ENV PATH=$PATH:/opt/android-sdk/emulator
