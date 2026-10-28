# Reproducible build environment for the PleatView Android TV app.
# Used by tools/build-apk.sh so the APK can be built on machines without
# Android Studio / an Android SDK installed.
FROM eclipse-temurin:21-jdk-noble

ARG CMDLINE_TOOLS=16111833
ARG COMPILE_SDK=37.0
ARG BUILD_TOOLS=36.0.0

ENV ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk
ENV PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

RUN apt-get update \
 && apt-get install -y --no-install-recommends unzip curl git \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p "$ANDROID_HOME/cmdline-tools" \
 && curl -fsSL -o /tmp/cmdline.zip \
      "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
 && unzip -q /tmp/cmdline.zip -d "$ANDROID_HOME/cmdline-tools" \
 && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest" \
 && rm /tmp/cmdline.zip

RUN yes | sdkmanager --licenses > /dev/null \
 && sdkmanager --install "platform-tools" "platforms;android-${COMPILE_SDK}" "build-tools;${BUILD_TOOLS}" \
 && chmod -R a+rwX "$ANDROID_HOME"

WORKDIR /work
