#!/usr/bin/env bash


error_exit() {
  echo " $1"
  if [[ -n $STEAM_ZENITY ]]; then
    $STEAM_ZENITY --error --text "$1"
  else 
    zenity --error --text "$1" || echo "Zenity failed to display error"
  fi
  logger -t fgmod "ERROR: $1"
  exit 1
}

# === CONFIG ===
fgmod_path="$HOME/fgmod"
dll_name="${DLL:-dxgi.dll}"
preserve_ini="${PRESERVE_INI:-true}"
fsr4_variant="${FGMOD_FSR4_VARIANT:-}"
python_bin="$(command -v python3 || command -v python || true)"

# === Resolve Game Path ===
if [[ "$#" -lt 1 ]]; then
  error_exit "Usage: $0 program [program_arguments...]"
fi

exe_folder_path=""
if [[ $# -eq 1 ]]; then
  [[ "$1" == *.exe ]] && exe_folder_path=$(dirname "$1") || exe_folder_path="$1"
else
  for arg in "$@"; do
    if [[ "$arg" == *.exe ]]; then
      [[ "$arg" == *"Cyberpunk 2077"* ]] && arg=${arg//REDprelauncher.exe/bin/x64/Cyberpunk2077.exe}
      [[ "$arg" == *"Witcher 3"* ]]      && arg=${arg//REDprelauncher.exe/bin/x64_dx12/witcher3.exe}
      [[ "$arg" == *"Baldurs Gate 3"* ]] && arg=${arg//Launcher\/LariLauncher.exe/bin/bg3_dx11.exe}
      [[ "$arg" == *"HITMAN 3"* ]]       && arg=${arg//Launcher.exe/Retail/HITMAN3.exe}
      [[ "$arg" == *"HITMAN World of Assassination"* ]] && arg=${arg//Launcher.exe/Retail/HITMAN3.exe}
      [[ "$arg" == *"SYNCED"* ]]         && arg=${arg//Launcher\/sop_launcher.exe/SYNCED.exe}
      [[ "$arg" == *"2KLauncher"* ]]     && arg=${arg//2KLauncher\/LauncherPatcher.exe/DoesntMatter.exe}
      [[ "$arg" == *"Warhammer 40,000 DARKTIDE"* ]] && arg=${arg//launcher\/Launcher.exe/binaries/Darktide.exe}
      [[ "$arg" == *"Warhammer Vermintide 2"* ]]    && arg=${arg//launcher\/Launcher.exe/binaries_dx12/vermintide2_dx12.exe}
      [[ "$arg" == *"Satisfactory"* ]]   && arg=${arg//FactoryGameSteam.exe/Engine/Binaries/Win64/FactoryGameSteam-Win64-Shipping.exe}
      [[ "$arg" == *"FINAL FANTASY XIV Online"* ]] && arg=${arg//boot\/ffxivboot.exe/game/ffxiv_dx11.exe}
      exe_folder_path=$(dirname "$arg")
      break
    fi
  done
fi

for arg in "$@"; do
  if [[ "$arg" == lutris:rungameid/* ]]; then
    lutris_id="${arg#lutris:rungameid/}"

    # Get slug from Lutris JSON
    slug=$(lutris --list-games --json 2>/dev/null | jq -r ".[] | select(.id == $lutris_id) | .slug")

    if [[ -z "$slug" || "$slug" == "null" ]]; then
      echo "Could not find slug for Lutris ID $lutris_id"
      break
    fi

    # Find matching YAML file using slug
    config_file=$(find ~/.config/lutris/games/ -iname "${slug}-*.yml" | head -1)

    if [[ -z "$config_file" ]]; then
      echo "No config file found for slug '$slug'"
      break
    fi

    # Extract executable path from YAML
    exe_path=$(grep -E '^\s*exe:' "$config_file" | sed 's/.*exe:[[:space:]]*//' )

    if [[ -n "$exe_path" ]]; then
      exe_folder_path=$(dirname "$exe_path")
      echo "Resolved executable path: $exe_path"
      echo "Executable folder: $exe_folder_path"
    else
      echo "Executable path not found in $config_file"
    fi

    break
  fi
done

[[ -z "$exe_folder_path" && -n "$STEAM_COMPAT_INSTALL_PATH" ]] && exe_folder_path="$STEAM_COMPAT_INSTALL_PATH"

if [[ -d "$exe_folder_path/Engine" ]]; then
  ue_exe=$(find "$exe_folder_path" -maxdepth 4 -mindepth 4 -path "*Binaries/Win64/*.exe" -not -path "*/Engine/*" | head -1)
  exe_folder_path=$(dirname "$ue_exe")
fi

[[ ! -d "$exe_folder_path" ]] && error_exit " Could not resolve game directory!"
[[ ! -w "$exe_folder_path" ]] && error_exit " No write permission to the game folder!"

logger -t fgmod "Target directory: $exe_folder_path"
logger -t fgmod "Using DLL name: $dll_name"
logger -t fgmod "Preserve INI: $preserve_ini"

# Both Decky and launch wrappers use the same verified, reversible installer.
[[ -n "$python_bin" ]] || error_exit "Python 3 is required"
patch_args=(patch "$exe_folder_path" --bundle "$fgmod_path" --dll "$dll_name")
[[ -n "$fsr4_variant" ]] && patch_args+=(--variant "$fsr4_variant")
[[ "$preserve_ini" != "true" ]] && patch_args+=(--reset-ini)
"$python_bin" "$fgmod_path/patch-game.py" "${patch_args[@]}" || error_exit "OptiScaler installation failed"
if [[ -f "$fgmod_path/update-optiscaler-config.py" ]]; then
  "$python_bin" "$fgmod_path/update-optiscaler-config.py" "$exe_folder_path/OptiScaler.ini" || error_exit "Could not update settings"
fi

if [[ $# -gt 1 || "$1" == *.exe ]]; then
  export SteamDeck=0
  if [[ "$dll_name" == *.dll ]]; then
    export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+$WINEDLLOVERRIDES;}${dll_name%.dll}=n,b"
  fi
  while [[ $# -gt 0 && "$1" == "--" ]]; do shift; done
  exec "$@"
fi
