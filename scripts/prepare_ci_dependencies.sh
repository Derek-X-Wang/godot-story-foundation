#!/usr/bin/env bash
# Optional live dependencies for the existing Ubuntu CI audio and X11/OpenGL tests.
set -euo pipefail

fail() { printf 'CI dependency preflight: %s\n' "$*" >&2; exit 1; }
work="$(mktemp -d)"
trap 'rm -rf -- "$work"' EXIT

installed() {
    [[ "$(dpkg-query -W -f='${db:Status-Status}' "$1" 2>/dev/null)" == installed ]]
}

missing=()
need_tool() {
    local tool=$1 package=$2 item
    if command -v "$tool" >/dev/null; then
        return
    fi
    if installed "$package"; then
        fail "$package is installed but $tool is not on PATH"
    fi
    for item in "${missing[@]}"; do
        [[ "$item" != "$package" ]] || return 0
    done
    missing+=("$package")
}

probe_audio() {
    local codec
    if ! timeout -k 2s 10s ffmpeg -nostdin -v error -y -f lavfi         -i 'anullsrc=r=8000:cl=mono' -t 0.05 -c:a pcm_s16le "$work/probe.wav"; then
        fail 'ffmpeg could not create a short PCM WAV'
    fi
    if ! codec="$(timeout -k 2s 10s ffprobe -v error -select_streams a:0         -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 "$work/probe.wav")"; then
        fail 'ffprobe could not read the generated PCM WAV'
    fi
    [[ "$codec" == pcm_s16le ]] || fail "ffprobe returned unexpected audio codec: $codec"
    printf 'Ready: ffmpeg and ffprobe PCM smoke passed.\n'
}

probe_xvfb() {
    if ! timeout -k 2s 15s xvfb-run -a -e /dev/stderr bash -ec \
        '[[ -n "${DISPLAY:-}" && -n "${XAUTHORITY:-}" && -n "$(xauth nlist "$DISPLAY")" ]]'; then
        fail 'xvfb-run could not start an X11 display with an xauth cookie'
    fi
    printf 'Ready: Xvfb/xauth startup passed.\n'
}

prepare_packages() {
    need_tool ffmpeg ffmpeg
    need_tool ffprobe ffmpeg
    need_tool xvfb-run xvfb
    need_tool Xvfb xvfb
    need_tool xauth xauth
    # apt package presence chooses the install list. Actual Mesa/OpenGL
    # activation is checked with the verified engine after it is downloaded.
    if ! installed libgl1-mesa-dri; then
        missing+=(libgl1-mesa-dri)
    fi
    if (( ${#missing[@]} == 0 )); then
        printf 'Required commands/Mesa package present; skipping apt.\n'
    else
        printf 'Installing missing CI packages from configured Ubuntu sources: %s\n' "${missing[*]}"
        local -a apt=(apt-get -o Acquire::Retries=1 -o Acquire::http::Timeout=10
            -o Acquire::https::Timeout=10 -o DPkg::Lock::Timeout=10)
        if ! sudo -n timeout -k 5s 90s "${apt[@]}" -o APT::Update::Error-Mode=any update; then
            fail 'apt update failed or exceeded 90s; required CI packages were not prepared'
        fi
        if ! sudo -n env DEBIAN_FRONTEND=noninteractive timeout -k 5s 240s \
            "${apt[@]}" install --no-install-recommends -y "${missing[@]}"; then
            fail 'apt install failed or exceeded 240s; required CI packages were not prepared'
        fi
    fi
    probe_audio
    probe_xvfb
}

probe_renderer() {
    local script_dir
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    cp -- "$script_dir/probe_ci_opengl.gd" "$work/probe_ci_opengl.gd"
    printf 'config_version=5\n' > "$work/project.godot"
    if ! timeout -k 3s 30s env LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a -e /dev/stderr \
        "${GODOT:-godot}" --display-driver x11 --rendering-method gl_compatibility --audio-driver Dummy \
        --path "$work" --script res://probe_ci_opengl.gd > "$work/godot.log" 2>&1; then
        cat "$work/godot.log" >&2
        fail 'Godot could not initialize X11/Compatibility OpenGL with software rendering requested'
    fi
    cat "$work/godot.log"
    if ! grep -q '^CI OpenGL ready: ' "$work/godot.log" ||
        grep -Eq '^[[:space:]]*(SCRIPT ERROR:|ERROR:)' "$work/godot.log"; then
        fail 'Godot exited without a clean non-headless OpenGL readiness result'
    fi
}

case "${1:-}" in
    prepare-packages) prepare_packages ;;
    probe-renderer) probe_renderer ;;
    *) fail 'usage: prepare_ci_dependencies.sh {prepare-packages|probe-renderer}' ;;
esac
