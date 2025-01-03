#!/usr/bin/env bash

# Set strict error handling
set -euo pipefail

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# Installation paths
readonly INSTALL_DIR="$HOME/.local/bin"
readonly NAUTILUS_SCRIPTS_DIR="$HOME/.local/share/nautilus/scripts"

# Supported formats
declare -A AUDIO_FORMATS=(
    ["mp3"]="MPEG Layer-3 Audio"
    ["aac"]="Advanced Audio Coding"
    ["wav"]="Waveform Audio"
    ["flac"]="Free Lossless Audio Codec"
    ["ogg"]="Ogg Vorbis Audio"
    ["m4a"]="MPEG-4 Audio"
    ["wma"]="Windows Media Audio"
    ["opus"]="Opus Audio"
    ["ac3"]="Dolby Digital Audio"
    ["amr"]="Adaptive Multi-Rate Audio"
)

declare -A VIDEO_FORMATS=(
    ["mp4"]="MPEG-4 Video"
    ["mkv"]="Matroska Video"
    ["avi"]="Audio Video Interleave"
    ["webm"]="WebM Video"
    ["mov"]="QuickTime Video"
    ["flv"]="Flash Video"
    ["wmv"]="Windows Media Video"
    ["m4v"]="MPEG-4 Video"
    ["3gp"]="3GPP Video"
    ["ts"]="MPEG Transport Stream"
)

# Print functions
print_step() { echo -e "${BLUE}==> $1${NC}"; }
print_success() { echo -e "${GREEN}✔ $1${NC}"; }
print_error() { echo -e "${RED}ERROR: $1${NC}" >&2; }

# Check dependencies
check_dependencies() {
    local missing_deps=()
    for cmd in ffmpeg ffprobe zenity; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        echo "Please install them using your package manager:"
        echo "For Ubuntu/Debian: sudo apt install ffmpeg zenity"
        echo "For Fedora: sudo dnf install ffmpeg zenity"
        echo "For Arch Linux: sudo pacman -S ffmpeg zenity"
        exit 1
    fi
}

# Create converter script
create_converter_script() {
    print_step "Creating converter script..."
    mkdir -p "$INSTALL_DIR"

    cat > "$INSTALL_DIR/media-converter" << 'EOL'
#!/usr/bin/env bash

# Set strict error handling
set -euo pipefail

# Function to get media duration in seconds
get_duration() {
    local file="$1"
    local duration
    duration=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$file" 2>/dev/null)
    if [[ -n "$duration" && "$duration" != "N/A" ]]; then
        echo "${duration%.*}" # Remove decimal part
    else
        echo "0"
    fi
}

# Check if file is a media file and get its type
check_media_type() {
    local file="$1"
    local mime_type
    
    # Get MIME type
    mime_type=$(file -b --mime-type "$file")
    
    if [[ $mime_type == audio/* ]]; then
        echo "audio"
    elif [[ $mime_type == video/* ]]; then
        echo "video"
    else
        # Use ffprobe as fallback
        if ffprobe -v quiet -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$file" 2>/dev/null; then
            echo "video"
        elif ffprobe -v quiet -select_streams a:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$file" 2>/dev/null; then
            echo "audio"
        else
            echo "invalid"
        fi
    fi
}

# Get conversion options based on format
get_conversion_opts() {
    local output_format="$1"
    local format_type="$2"
    
    case "$output_format" in
        mp3) echo "-c:a libmp3lame -q:a 2" ;;
        aac) echo "-c:a aac -b:a 192k" ;;
        flac) echo "-c:a flac" ;;
        ogg) echo "-c:a libvorbis -q:a 4" ;;
        opus) echo "-c:a libopus -b:a 128k" ;;
        mp4) echo "-c:v libx264 -crf 23 -preset medium -c:a aac -b:a 192k" ;;
        webm) echo "-c:v libvpx-vp9 -crf 30 -b:v 0 -c:a libopus -b:a 128k" ;;
        *) 
            if [[ "$format_type" == "audio" ]]; then
                echo "-c:a libmp3lame -q:a 2"
            else
                echo "-c:v libx264 -crf 23 -preset medium -c:a aac -b:a 192k"
            fi
            ;;
    esac
}

# Function to convert a single file
convert_file() {
    local input_file="$1"
    local output_format="$2"
    local progress_file="$3"
    local dialog_id="$4"
    local total_files="$5"
    local current_file="$6"
    
    # Get file type and validate
    local file_type
    file_type=$(check_media_type "$input_file")
    
    if [[ "$file_type" == "invalid" ]]; then
        zenity --error --text="Not a valid media file: $(basename "$input_file")" --width=400
        return 1
    fi
    
    # Determine format type
    local format_type
    case "$output_format" in
        mp3|aac|wav|flac|ogg|m4a|wma|opus|ac3|amr) format_type="audio" ;;
        mp4|mkv|avi|webm|mov|flv|wmv|m4v|3gp|ts) format_type="video" ;;
        *) 
            zenity --error --text="Unsupported format: $output_format" --width=300
            return 1
            ;;
    esac
    
    if [[ "$file_type" == "audio" && "$format_type" == "video" ]]; then
        zenity --error --text="Cannot convert audio to video: $(basename "$input_file")" --width=400
        return 1
    fi
    
    # Generate output filename
    local base_name output_dir output_file
    base_name=$(basename "$input_file" | sed 's/\.[^.]*$//')
    output_dir=$(dirname "$input_file")
    output_file="$output_dir/${base_name}_converted.${output_format}"
    
    # Get conversion options
    local conversion_opts
    conversion_opts=$(get_conversion_opts "$output_format" "$format_type")
    
    # Get duration
    local duration
    duration=$(get_duration "$input_file")
    
    # Build ffmpeg command
    local ffmpeg_cmd
    if [[ "$format_type" == "audio" && "$file_type" == "video" ]]; then
        ffmpeg_cmd="ffmpeg -i \"$input_file\" -vn $conversion_opts \"$output_file\""
    else
        ffmpeg_cmd="ffmpeg -i \"$input_file\" $conversion_opts \"$output_file\""
    fi
    
    # Start conversion and progress monitoring
    (
        # Convert command string to array for proper execution
        eval "$ffmpeg_cmd -progress \"$progress_file\" 2>/dev/null" &
        local ffmpeg_pid=$!
        
        while kill -0 $ffmpeg_pid 2>/dev/null; do
            if [[ -f "$progress_file" ]]; then
                local current_time
                current_time=$(grep -oP 'out_time=\K[0-9:.]*' "$progress_file" 2>/dev/null | tail -n1)
                if [[ -n "$current_time" ]]; then
                    local current_seconds
                    current_seconds=$(echo "$current_time" | awk -F: '{print ($1 * 3600) + ($2 * 60) + $3}')
                    if [[ $duration -gt 0 && -n "$current_seconds" ]]; then
                        local percentage
                        percentage=$(( (current_seconds * 100) / duration ))
                        if [[ $percentage -le 100 ]]; then
                            echo "$percentage"
                            echo "# File $current_file of $total_files: $(basename "$input_file") ($percentage%)"
                        fi
                    fi
                fi
            fi
            sleep 0.1
        done
        
        wait $ffmpeg_pid
        echo "100"
        echo "# Completed: $(basename "$input_file")"
    ) | zenity --progress \
        --title="Converting Media" \
        --text="Starting conversion..." \
        --percentage=0 \
        --auto-close \
        --window-icon=info \
        --width=400 \
        --dialog-id="$dialog_id" || {
        pkill -P $$ ffmpeg
        return 1
    }
    
    # Verify output file
    if [[ ! -f "$output_file" || ! -s "$output_file" ]]; then
        return 1
    fi
    
    return 0
}

# Main conversion handler
main() {
    local output_format="$1"
    shift
    local input_files=("$@")
    local total_files=${#input_files[@]}
    
    if [[ $total_files -eq 0 ]]; then
        zenity --error --text="No input files provided" --width=300
        exit 1
    fi
    
    # Create temporary directory for progress files
    local temp_dir
    temp_dir=$(mktemp -d)
    trap 'rm -rf "$temp_dir"' EXIT
    
    # Process each file
    local success_count=0
    local failed_files=()
    
    for ((i=0; i<${#input_files[@]}; i++)); do
        local input_file="${input_files[i]}"
        local progress_file="$temp_dir/progress_$i"
        local current_file=$((i + 1))
        
        if convert_file "$input_file" "$output_format" "$progress_file" "$i" "$total_files" "$current_file"; then
            ((success_count++))
        else
            failed_files+=("$(basename "$input_file")")
        fi
    done
    
    # Show summary
    if [[ ${#failed_files[@]} -eq 0 ]]; then
        zenity --info \
            --title="Conversion Complete" \
            --text="Successfully converted all $total_files files." \
            --width=300
    else
        local failed_msg="Converted $success_count of $total_files files.\n\nFailed files:\n"
        printf -v failed_msg "%s\n" "${failed_files[@]}"
        zenity --warning \
            --title="Conversion Complete" \
            --text="$failed_msg" \
            --width=400
    fi
}

# Start conversion with all provided files
main "$@"
EOL

    chmod +x "$INSTALL_DIR/media-converter"
    print_success "Converter script created"
}

# Create Nautilus scripts for formats
create_nautilus_scripts() {
    print_step "Creating Nautilus scripts..."
    
    # Create Audio conversion menu
    mkdir -p "$NAUTILUS_SCRIPTS_DIR/Media Converter/Audio"
    for format in "${!AUDIO_FORMATS[@]}"; do
        script_name="$NAUTILUS_SCRIPTS_DIR/Media Converter/Audio/To ${format^^} (${AUDIO_FORMATS[$format]})"
        cat > "$script_name" << EOL
#!/bin/bash
"$INSTALL_DIR/media-converter" "$format" "\$@"
EOL
        chmod +x "$script_name"
    done

    # Create Video conversion menu
    mkdir -p "$NAUTILUS_SCRIPTS_DIR/Media Converter/Video"
    for format in "${!VIDEO_FORMATS[@]}"; do
        script_name="$NAUTILUS_SCRIPTS_DIR/Media Converter/Video/To ${format^^} (${VIDEO_FORMATS[$format]})"
        cat > "$script_name" << EOL
#!/bin/bash
"$INSTALL_DIR/media-converter" "$format" "\$@"
EOL
        chmod +x "$script_name"
    done

    print_success "Nautilus scripts created"
}

# Main installation function
main() {
    print_step "Checking dependencies..."
    check_dependencies
    print_success "Dependencies are satisfied"

    create_converter_script
    create_nautilus_scripts

    print_success "Installation complete!"
    echo "Restart your file manager to see the new scripts in the context menu -> Scripts -> Media Converter -> [Audio/Video]."
}

main
