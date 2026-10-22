# Android emulator runtime for Castlevania: Grimoire of Souls
#
# Rationale (see aes/shadow/SD-RT-001 for the full argument):
#   The APK ships native-code for arm64-v8a + armeabi-v7a only. The Steam Deck
#   is x86_64. Google's API 30+ x86_64 system images ship the ARM native bridge
#   (libndk_translation), so an ARM-only Unity/Il2CPP app runs on x86_64 under
#   KVM acceleration instead of full-system ARM emulation.
#
# API 30 is the release Google explicitly documented as "ARM compatible".
# The game declares minSdk 21 / targetSdk 28, so API 30 satisfies it.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_AVD_HOME=/opt/android-sdk/avd
ENV PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/emulator:$PATH

# Runtime deps for the emulator: X11/GL for -gpu host, PulseAudio for audio,
# Mesa DRI so hardware GL passthrough works via /dev/dri.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl unzip xz-utils \
        openjdk-17-jre-headless \
        libgl1 libglx-mesa0 libegl1 libgles2 \
        libglu1-mesa libgl1-mesa-dri libglx-mesa0 \
        libpulse0 libasound2t64 \
        libx11-6 libx11-xcb1 libxcb1 libxcb-glx0 libxcb-dri2-0 libxcb-dri3-0 \
        libxcb-present0 libxcb-sync1 libxcb-xfixes0 libxcb-shm0 libxcb-randr0 \
        libxcb-shape0 libxcb-render0 libxcb-image0 libxcb-keysyms1 libxcb-icccm4 \
        libxcb-xkb1 libxkbcommon0 \
        libxext6 libxfixes3 libxrender1 libxi6 libxtst6 libxdamage1 libxrandr2 \
        libxcursor1 libxcomposite1 libxinerama1 libnss3 libnspr4 libcups2 \
        libdbus-1-3 libfontconfig1 libfreetype6 libuuid1 \
        libxkbfile1 \
        zlib1g libstdc++6 \
        xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
# Install frida-tools CLI for Java hooking
RUN pip3 install frida-tools 2>&1 | tail -3 || true

# Android command-line tools
ARG CLT_ZIP=commandlinetools-linux-16111833_latest.zip
RUN curl -fsSL -o /tmp/clt.zip "https://dl.google.com/android/repository/${CLT_ZIP}" \
    && unzip -q /tmp/clt.zip -d /tmp/clt \
    && mkdir -p /opt/android-sdk/cmdline-tools \
    && mv /tmp/clt/cmdline-tools /opt/android-sdk/cmdline-tools/latest \
    && rm -rf /tmp/clt /tmp/clt.zip

# Accept licenses, then install the pieces we need.
ARG SYS_IMAGE="system-images;android-30;google_apis;x86_64"
RUN yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses > /dev/null 2>&1 || true
RUN /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --install \
        "platform-tools" \
        "emulator" \
        "${SYS_IMAGE}" \
    && rm -rf /opt/android-sdk/.temp /opt/android-sdk/.knownPackages

# Install frida-server for dynamic instrumentation (license check bypass)
RUN curl -fsSL --retry 3 -o /tmp/frida-server.xz \
        "https://github.com/frida/frida/releases/download/16.2.1/frida-server-16.2.1-android-x86_64.xz" \
    && ls -la /tmp/frida-server.xz \
    && xz -d /tmp/frida-server.xz -c > /usr/local/bin/frida-server \
    && chmod +x /usr/local/bin/frida-server \
    && rm -f /tmp/frida-server.xz
ENV PATH=/usr/local/bin:$PATH

# AVD definition. hw.gpu.mode=host uses host GPU via DRI passthrough.
# For software fallback use: -e GPU_MODE=swiftshader_indirect at runtime.
RUN echo "sdk.dir=/opt/android-sdk" > /root/.android/repositories.cfg \
    && mkdir -p /root/.android \
    && avdmanager create avd -n cvgos -k "${SYS_IMAGE}" --force \
         --device "pixel_4" \
    && sed -i \
         -e 's/^hw.gpu.mode=.*/hw.gpu.mode=host/' \
         -e 's/^hw.ramSize=.*/hw.ramSize=4096/' \
         -e 's/^hw.cpu.ncore=.*/hw.cpu.ncore=6/' \
         -e 's/^disk.dataPartition.size=.*/disk.dataPartition.size=12G/' \
         -e 's/^hw.keyboard=yes/hw.keyboard=yes/' \
         -e 's/^hw.lcd.width=.*/hw.lcd.width=1920/' \
         -e 's/^hw.lcd.height=.*/hw.lcd.height=1080/' \
         -e 's/^hw.lcd.density=.*/hw.lcd.density=320/' \
         /root/.android/avd/cvgos.avd/config.ini \
    && printf 'hw.keyboard=yes\n' >> /root/.android/avd/cvgos.avd/config.ini

WORKDIR /opt/android-sdk
EXPOSE 5554 5555

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["emulator"]