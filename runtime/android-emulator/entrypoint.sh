#!/usr/bin/env bash
# Entrypoint for the Android emulator runtime.
#
# Modes:
#   emulator        (default) start the AVD and block
#   install <apk>  install an APK into the running AVD
#   launch <pkg>   force-stop + start an app's main activity
#   shell          interactive shell
#   adb <args...>  run adb against the local emulator
#   waitboot       block until the device reports sys.boot_completed=1
set -uo pipefail

AVD="${AVD:-cvgos}"
ADB="adb -s ${ADB_SERIAL:-emulator-5554}"
APK_DIR="${APK_DIR:-/apks}"

log() { printf '[android-emulator] %s\n' "$*" >&2; }

wait_for_adb() {
    local tries=${1:-90}
    log "waiting for adb device ${ADB_SERIAL:-emulator-5554} ..."
    for _ in $(seq 1 "${tries}"); do
        if adb devices | awk '{print $1}' | grep -qx "${ADB_SERIAL:-emulator-5554}"; then
            if [ "$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
                log "device booted"
                return 0
            fi
        fi
        sleep 2
    done
    log "ERROR: device did not boot in time"
    return 1
}

case "${1:-emulator}" in
    emulator)
        shift || true
        extra_args=("$@")
        GPU_MODE="${GPU_MODE:-host}"
        # Start Xvfb for host GPU mode (provides virtual display via /dev/dri)
        if [ "${GPU_MODE}" = "host" ]; then
            log "starting Xvfb virtual display for host GPU mode"
            Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp -nolisten unix &
            XVFB_PID=$!
            export DISPLAY=:99
            sleep 2
            # Verify Xvfb is running
            if kill -0 $XVFB_PID 2>/dev/null; then
                log "Xvfb started (PID $XVFB_PID)"
            else
                log "WARNING: Xvfb failed to start, falling back to qemu_gpu"
                GPU_MODE="qemu_gpu"
            fi
        fi
        log "starting AVD ${AVD} (gpu=${GPU_MODE}, audio=$( [ "${NO_AUDIO:-0}" = "1" ] && echo off || echo on ))"
        exec emulator \
            -avd "${AVD}" \
            -gpu "${GPU_MODE}" \
            -memory "${EMULATOR_MEMORY:-4096}" \
            -cores "${EMULATOR_CORES:-4}" \
            -no-boot-anim \
            -no-snapshot \
            -netdelay none \
            -netspeed full \
            -no-window \
            ${NO_AUDIO:+-no-audio} \
            "${extra_args[@]}"
        ;;

    waitboot)
        wait_for_adb "${2:-90}"
        ;;

    install)
        apk="$2"
        [ -f "${apk}" ] || apk="${APK_DIR}/$(basename "$2")"
        [ -f "${apk}" ] || { log "ERROR: apk not found: $2"; exit 1; }
        wait_for_adb 90 || exit 1
        log "installing ${apk}"
        # -r = reinstall, -d = allow version downgrade, -g = grant runtime perms
        $ADB install -r -d -g "${apk}"
        ;;

    launch)
        pkg="$2"
        wait_for_adb 90 || exit 1
        log "launching ${pkg}"
        $ADB shell am force-stop "${pkg}"
        $ADB shell monkey -p "${pkg}" -c android.intent.category.LAUNCHER 1
        ;;

    adb)
        shift
        exec adb "$@"
        ;;

    shell)
        exec bash
        ;;

    *)
        exec "$@"
        ;;
esac
