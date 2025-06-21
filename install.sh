#!/usr/bin/env bash

# Set strict error handling
set -euo pipefail

# Colors for terminal output (used during installation)
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
    ["opus"]="Opus Audio"
    ["wma"]="Windows Media Audio"
    ["alac"]="Apple Lossless Audio Codec"
    ["ac3"]="Dolby Digital Audio"
    ["amr"]="Adaptive Multi-Rate Audio"
    ["aiff"]="Audio Interchange File Format"
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
    ["ogv"]="Ogg Video"
    ["vob"]="DVD Video Object"
)

declare -A IMAGE_FORMATS=(
    ["jpg"]="JPEG Image"
    ["png"]="Portable Network Graphics"
    ["webp"]="WebP Image"
    ["gif"]="Graphics Interchange Format"
    ["tiff"]="Tagged Image File Format"
    ["bmp"]="Bitmap Image"
    ["heif"]="High Efficiency Image Format"
    ["ico"]="Icon Image"
)

declare -A DOCUMENT_FORMATS=(
    ["pdf"]="Portable Document Format"
    ["docx"]="Microsoft Word Document"
    ["odt"]="OpenDocument Text"
    ["rtf"]="Rich Text Format"
    ["txt"]="Plain Text"
)

declare -A SUBTITLE_FORMATS=(
    ["srt"]="SubRip Subtitle"
    ["ass"]="Advanced SubStation Alpha"
)

declare -A ARCHIVE_FORMATS=(
    ["zip"]="ZIP Archive"
    ["tar"]="Tar Archive"
    ["tar.gz"]="Gzip Tar Archive"
    ["tar.bz2"]="Bzip2 Tar Archive"
)

# Print functions for installation feedback
print_step() { echo -e "${BLUE}==> $1${NC}"; }
print_success() { echo -e "${GREEN}✔ $1${NC}"; }
print_error() { echo -e "${RED}ERROR: $1${NC}" >&2; }

# Check dependencies
check_dependencies() {
    local missing_deps=()
    for cmd in ffmpeg ffprobe zenity unzip tar soffice unoconv gs; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        echo "Please install them using your package manager:"
        echo "For Ubuntu/Debian: sudo apt install ffmpeg zenity unzip tar libreoffice unoconv ghostscript"
        echo "For Fedora: sudo dnf install ffmpeg zenity unzip tar libreoffice-core unoconv ghostscript"
        echo "For Arch Linux: sudo pacman -S ffmpeg zenity unzip tar libreoffice unoconv ghostscript"
        exit 1
    fi
    # Warn about libheif for HEIF support
    if ! ffmpeg -hide_banner -codecs 2>/dev/null | grep -q libheif; then
        print_error "libheif not found; HEIF format may not work."
        echo "Install libheif for HEIF support (e.g., sudo apt install libheif-dev)."
    fi
}

# Generate unique output filename to avoid overwriting
generate_output_file() {
    local input_file="$1"
    local output_format="$2"
    local base_name output_dir output_file
    base_name=$(basename "$input_file" | sed 's/\.[^.]*$//')
    output_dir=$(dirname "$input_file")
    output_file="$output_dir/${base_name}_converted.${output_format}"
    local counter=1
    while [[ -f "$output_file" ]]; do
        output_file="$output_dir/${base_name}_converted_${counter}.${output_format}"
        ((counter++))
    done
    echo "$output_file"
}

# Generate output filename pattern for multi-page outputs
generate_multi_output_file() {
    local input_file="$1"
    local output_format="$2"
    local base_name output_dir output_file
    base_name=$(basename "$input_file" | sed 's/\.[^.]*$//')
    output_dir=$(dirname "$input_file")
    output_file="$output_dir/${base_name}_converted_%03d.${output_format}"
    local counter=1
    while [[ -f "${output_file//%03d/001}" ]]; do
        output_file="$output_dir/${base_name}_converted_${counter}_%03d.${output_format}"
        ((counter++))
    done
    echo "$output_file"
}

# Get media duration in seconds (for video/audio only)
get_duration() {
    local file="$1"
    local duration
    duration=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$file" 2>/dev/null)
    if [[ -n "$duration" && "$duration" != "N/A" ]]; then
        echo "${duration%.*}"
    else
        echo "0"
    fi
}

# Check if file is audio, video, image, document, subtitle, or archive
check_media_type() {
    local file="$1"
    local extension="${file##*.}"
    extension=$(echo "$extension" | tr '[:upper:]' '[:lower:]')
    case "$extension" in
        pdf|docx|odt|rtf|txt) echo "document"; return ;;
        srt|ass) echo "subtitle"; return ;;
        zip|tar) echo "archive"; return ;;
        tar.gz) echo "archive"; return ;;
        tar.bz2) echo "archive"; return ;;
    esac
    local codec_name
    codec_name=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$file" 2>/dev/null)
    case "$codec_name" in
        mjpeg|png|webp|gif|tiff|bmp|heif|ico)
            echo "image"
            ;;
        *)
            local video_streams=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$file" 2>/dev/null | grep -c "video" || true)
            local audio_streams=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$file" 2>/dev/null | grep -c "audio" || true)
            if [[ $video_streams -gt 0 ]]; then
                echo "video"
            elif [[ $audio_streams -gt 0 ]]; then
                echo "audio"
            else
                echo "invalid"
            fi
            ;;
    esac
}

# Extract archive and return list of media files
extract_archive() {
    local archive_file="$1"
    local temp_dir="$2"
    local extension="${archive_file##*.}"
    extension=$(echo "$extension" | tr '[:upper:]' '[:lower:]')
    local media_files=()

    case "$extension" in
        zip)
            unzip -q "$archive_file" -d "$temp_dir" || {
                zenity --error --text="Failed to extract ZIP archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        tar)
            tar -xf "$archive_file" -C "$temp_dir" || {
                zenity --error --text="Failed to extract TAR archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        tar.gz)
            tar -xzf "$archive_file" -C "$temp_dir" || {
                zenity --error --text="Failed to extract TAR.GZ archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        tar.bz2)
            tar -xjf "$archive_file" -C "$temp_dir" || {
                zenity --error --text="Failed to extract TAR.BZ2 archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        *)
            zenity --error --text="Unsupported archive format: $extension" --width=300
            return 1
            ;;
    esac

    # Find supported media files in extracted archive
    while IFS= read -r -d '' file; do
        local file_type
        file_type=$(check_media_type "$file")
        if [[ "$file_type" != "invalid" && "$file_type" != "archive" ]]; then
            media_files+=("$file")
        fi
    done < <(find "$temp_dir" -type f -print0)
    echo "${media_files[@]}"
}

# Convert document to another document format or PDF for image conversion
convert_document() {
    local input_file="$1"
    local output_format="$2"
    local output_file="$3"
    local is_image_output="$4" # true if converting to image

    if [[ "$is_image_output" == "true" ]]; then
        # Convert to PDF first for image output
        local temp_pdf
        temp_pdf=$(mktemp --suffix=.pdf)
        if [[ "${input_file##*.}" != "pdf" ]]; then
            unoconv -f pdf -o "$temp_pdf" "$input_file" || {
                soffice --headless --convert-to pdf --outdir "$(dirname "$temp_pdf")" "$input_file" >/dev/null 2>&1 || {
                    zenity --error --text="Failed to convert $(basename "$input_file") to PDF" --width=400
                    rm -f "$temp_pdf"
                    return 1
                }
                mv "$(dirname "$temp_pdf")/$(basename "$input_file" | sed 's/\.[^.]*$//').pdf" "$temp_pdf"
            }
        else
            cp "$input_file" "$temp_pdf"
        fi
        echo "$temp_pdf"
        return 0
    else
        # Direct document-to-document conversion
        unoconv -f "$output_format" -o "$output_file" "$input_file" || {
            soffice --headless --convert-to "$output_format" --outdir "$(dirname "$output_file")" "$input_file" >/dev/null 2>&1 || {
                zenity --error --text="Failed to convert $(basename "$input_file") to $output_format" --width=400
                return 1
            }
            mv "$(dirname "$output_file")/$(basename "$input_file" | sed 's/\.[^.]*$//').$output_format" "$output_file"
        }
        return 0
    fi
}

# Get FFmpeg conversion options based on format
get_conversion_opts() {
    local output_format="$1"
    case "$output_format" in
        mp3) echo "-c:a libmp3lame -q:a 2" ;;
        aac) echo "-c:a aac -b:a 192k" ;;
        flac) echo "-c:a flac" ;;
        ogg) echo "-c:a libvorbis -q:a 4" ;;
        wav) echo "-c:a pcm_s16le" ;;
        m4a) echo "-c:a aac -b:a 192k" ;;
        opus) echo "-c:a libopus -b:a 128k" ;;
        wma) echo "-c:a wmav2 -b:a 128k" ;;
        alac) echo "-c:a alac" ;;
        ac3) echo "-c:a ac3 -b:a 256k" ;;
        amr) echo "-c:a amr_nb -b:a 12.2k" ;;
        aiff) echo "-c:a pcm_s16le -f aiff" ;;
        mp4) echo "-c:v libx264 -crf 23 -preset medium -c:a aac -b:a 192k" ;;
        mkv) echo "-c:v libx264 -crf 23 -c:a aac -b:a 192k" ;;
        avi) echo "-c:v mpeg4 -c:a mp3 -q:a 2" ;;
        webm) echo "-c:v libvpx-vp9 -crf 30 -b:v 0 -c:a libopus -b:a 128k" ;;
        mov) echo "-c:v libx264 -crf 23 -c:a aac -b:a 192k" ;;
        flv) echo "-c:v flv1 -c:a mp3 -b:a 128k" ;;
        wmv) echo "-c:v wmv2 -c:a wmav2 -b:a 128k" ;;
        m4v) echo "-c:v libx264 -crf 23 -c:a aac -b:a 192k" ;;
        3gp) echo "-c:v h263 -c:a amr_nb -b:a 12.2k" ;;
        ts) echo "-c:v mpeg2video -c:a mp2 -b:a 192k" ;;
        ogv) echo "-c:v libtheora -c:a libvorbis -q:v 7 -q:a 4" ;;
        vob) echo "-c:v mpeg2video -c:a ac3 -b:a 192k" ;;
        jpg) echo "-c:v mjpeg -q:v 2" ;;
        png) echo "-c:v png" ;;
        webp) echo "-c:v webp -quality 80" ;;
        gif) echo "-c:v gif" ;;
        tiff) echo "-c:v tiff" ;;
        bmp) echo "-c:v bmp" ;;
        heif) echo "-c:v libheif" ;;
        ico) echo "-c:v ico" ;;
        srt|ass) echo "" ;;
        *) echo "" ;;
    esac
}

# Convert a single file with progress feedback
convert_file() {
    local input_file="$1"
    local output_format="$2"
    local progress_file="$3"
    local current_file="$4"
    local total_files="$5"
    local pdf_mode="$6"

    # Check media type
    local file_type
    file_type=$(check_media_type "$input_file")
    if [[ "$file_type" == "invalid" ]]; then
        zenity --error --text="Not a valid media file: $(basename "$input_file")" --width=400
        return 1
    fi

    # Handle archive files
    if [[ "$file_type" == "archive" ]]; then
        local temp_dir
        temp_dir=$(mktemp -d)
        local media_files
        media_files=($(extract_archive "$input_file" "$temp_dir"))
        if [[ ${#media_files[@]} -eq 0 ]]; then
            zenity --error --text="No supported media files found in archive: $(basename "$input_file")" --width=400
            rm -rf "$temp_dir"
            return 1
        fi
        local success_count=0
        local failed_files=()
        for ((i=0; i<${#media_files[@]}; i++)); do
            local media_file="${media_files[i]}"
            local sub_progress_file="$progress_file.$i"
            if convert_file "$media_file" "$output_format" "$sub_progress_file" "$current_file" "$total_files" "$pdf_mode"; then
                ((success_count++))
            else
                failed_files+=("$(basename "$media_file")")
            fi
        done
        rm -rf "$temp_dir"
        if [[ ${#failed_files[@]} -eq 0 ]]; then
            return 0
        else
            zenity --error --text="Archive conversion failed for some files in $(basename "$input_file"):\n${failed_files[*]}" --width=400
            return 1
        fi
    fi

    # Determine output type
    local output_type
    case "$output_format" in
        mp3|aac|wav|flac|ogg|m4a|opus|wma|alac|ac3|amr|aiff) output_type="audio" ;;
        mp4|mkv|avi|webm|mov|flv|wmv|m4v|3gp|ts|ogv|vob) output_type="video" ;;
        jpg|png|webp|gif|tiff|bmp|heif|ico) output_type="image" ;;
        srt|ass) output_type="subtitle" ;;
        pdf|docx|odt|rtf|txt) output_type="document" ;;
        *) 
            zenity --error --text="Unsupported format: $output_format" --width=300
            return 1
            ;;
    esac

    # Validate conversion type
    if [[ "$output_type" == "audio" && "$file_type" != "audio" && "$file_type" != "video" ]]; then
        zenity --error --text="Cannot convert $file_type to audio: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$output_type" == "video" && "$file_type" != "video" && "$file_type" != "subtitle" ]]; then
        zenity --error --text="Cannot convert $file_type to video: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$output_type" == "image" && "$file_type" != "image" && "$file_type" != "document" ]]; then
        zenity --error --text="Can only convert images or documents to image formats: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$output_type" == "document" && "$file_type" != "document" ]]; then
        zenity --error --text="Can only convert documents to document formats: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$file_type" == "subtitle" && "$output_type" != "subtitle" && "$output_type" != "video" ]]; then
        zenity --error --text="Can only convert subtitles to subtitle or video formats: $(basename "$input_file")" --width=400
        return 1
    fi

    # Generate output file
    local output_file
    if [[ "$output_type" == "image" && "$file_type" == "document" && "$pdf_mode" == "multi" && "$output_format" != "gif" ]]; then
        output_file=$(generate_multi_output_file "$input_file" "$output_format")
    else
        output_file=$(generate_output_file "$input_file" "$output_format")
    fi

    # Handle document-to-document conversion
    if [[ "$output_type" == "document" ]]; then
        convert_document "$input_file" "$output_format" "$output_file" "false" || {
            return 1
        }
        echo "# Completed file $current_file of $total_files: $(basename "$input_file")"
        return 0
    fi

    # Handle document-to-image conversion
    local actual_input_file="$input_file"
    if [[ "$file_type" == "document" && "$output_type" == "image" ]]; then
        actual_input_file=$(convert_document "$input_file" "pdf" "" "true") || {
            return 1
        }
    fi

    # Get conversion options
    local conversion_opts
    conversion_opts=$(get_conversion_opts "$output_format")

    # Get duration for video/audio progress
    local duration=0
    if [[ "$file_type" == "video" || "$file_type" == "audio" ]]; then
        duration=$(get_duration "$actual_input_file")
    fi

    # Build FFmpeg command
    local ffmpeg_args=()
    if [[ "$file_type" == "document" && "$output_type" == "image" ]]; then
        if [[ "$pdf_mode" == "single" ]]; then
            ffmpeg_args=(-i "$actual_input_file" -vframes 1 "$output_file")
        else
            ffmpeg_args=(-i "$actual_input_file" "$output_file")
        fi
    elif [[ "$file_type" == "image" && "$output_type" == "image" ]]; then
        ffmpeg_args=(-i "$actual_input_file" $conversion_opts "$output_file")
    elif [[ "$file_type" == "document" && "${actual_input_file##*.}" == "txt" && "$output_type" == "image" ]]; then
        ffmpeg_args=(-f lavfi -i "color=c=white:s=1280x720" -vf "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile='$actual_input_file':fontcolor=black:fontsize=24:x=10:y=10" -frames:v 1 "$output_file")
    elif [[ "$file_type" == "video" && "$output_type" == "audio" ]]; then
        ffmpeg_args=(-i "$actual_input_file" -vn $conversion_opts "$output_file")
    elif [[ "$file_type" == "subtitle" && "$output_type" == "video" ]]; then
        ffmpeg_args=(-i "$actual_input_file" -vf "subtitles='$actual_input_file'" "$output_file")
    elif [[ "$file_type" == "subtitle" && "$output_type" == "subtitle" ]]; then
        ffmpeg_args=(-i "$actual_input_file" "$output_file")
    else
        ffmpeg_args=(-i "$actual_input_file" $conversion_opts "$output_file")
    fi

    # Run conversion and monitor progress
    (
        ffmpeg "${ffmpeg_args[@]}" -progress "$progress_file" 2>/dev/null &
        local ffmpeg_pid=$!

        while kill -0 $ffmpeg_pid 2>/dev/null; do
            if [[ -f "$progress_file" && "$file_type" != "image" && "$file_type" != "document" && "$file_type" != "subtitle" ]]; then
                local current_time
                current_time=$(grep -oP 'out_time=\K[0-9:.]*' "$progress_file" 2>/dev/null | tail -n1)
                if [[ -n "$current_time" && $duration -gt 0 ]]; then
                    local current_seconds
                    current_seconds=$(echo "$current_time" | awk -F: '{print ($1 * 3600) + ($2 * 60) + $3}')
                    local percentage
                    percentage=$(( (current_seconds * 100) / duration ))
                    if [[ $percentage -le 100 ]]; then
                        echo "$percentage"
                        echo "# File $current_file of $total_files: $(basename "$input_file") ($percentage%)"
                    fi
                else
                    echo "# Processing file $current_file of $total_files: $(basename "$input_file")"
                fi
            else
                echo "# Processing file $current_file of $total_files: $(basename "$input_file")"
            fi
            sleep 1
        done

        wait $ffmpeg_pid
        local ffmpeg_exit_status=$?
        if [[ $ffmpeg_exit_status -eq 0 && (-f "$output_file" || -f "${output_file//%03d/001}") && (-s "$output_file" || -s "${output_file//%03d/001}") ]]; then
            echo "100"
            echo "# Completed file $current_file of $total_files: $(basename "$input_file")"
            [[ "$actual_input_file" != "$input_file" ]] && rm -f "$actual_input_file"
            return 0
        else
            echo "# Conversion failed for file $current_file of $total_files: $(basename "$input_file")"
            [[ "$actual_input_file" != "$input_file" ]] && rm -f "$actual_input_file"
            return 1
        fi
    ) || {
        pkill -P $$ ffmpeg
        [[ "$actual_input_file" != "$input_file" ]] && rm -f "$actual_input_file"
        return 1
    }
}

# Main function to handle multiple files
main() {
    local output_format="$1"
    shift
    local input_files=("$@")
    local total_files=${#input_files[@]}
    local pdf_mode="single"

    if [[ $total_files -eq 0 ]]; then
        zenity --error --text="No input files provided" --width=300
        exit 1
    fi

    # Check if any input is a document and output is image, prompt for mode
    if [[ "$output_format" == "jpg" || "$output_format" == "png" || "$output_format" == "webp" || "$output_format" == "gif" || "$output_format" == "tiff" || "$output_format" == "bmp" || "$output_format" == "heif" || "$output_format" == "ico" ]]; then
        for input_file in "${input_files[@]}"; do
            if [[ $(check_media_type "$input_file") == "document" ]]; then
                pdf_mode=$(zenity --list --title="Document Conversion Mode" --text="Choose document conversion mode:" --column="Mode" --width=300 --height=200 \
                    "Single Page (First)" \
                    "All Pages (Separate Images)" \
                    "All Pages (Animated GIF)" || echo "single")
                case "$pdf_mode" in
                    "All Pages (Separate Images)") pdf_mode="multi" ;;
                    "All Pages (Animated GIF)") pdf_mode="multi"; output_format="gif" ;;
                    *) pdf_mode="single" ;;
                esac
                break
            fi
        done
    fi

    local temp_dir
    temp_dir=$(mktemp -d)
    trap 'rm -rf "$temp_dir"' EXIT

    (
        local success_count=0
        local failed_files=()
        for ((i=0; i<${#input_files[@]}; i++)); do
            local input_file="${input_files[i]}"
            local progress_file="$temp_dir/progress_$i"
            local current_file=$((i + 1))
            if convert_file "$input_file" "$output_format" "$progress_file" "$current_file" "$total_files" "$pdf_mode"; then
                ((success_count++))
            else
                failed_files+=("$(basename "$input_file")")
            fi
        done
        if [[ ${#failed_files[@]} -eq 0 ]]; then
            echo "# All $total_files files converted successfully."
        else
            local failed_msg="# Converted $success_count of $total_files files.\n\nFailed files:\n"
            printf -v failed_msg "$failed_msg%s\n" "${failed_files[@]}"
            echo "$failed_msg"
        fi
    ) | zenity --progress \
        --title="Converting Media" \
        --text="Starting conversion..." \
        --percentage=0 \
        --auto-close \
        --width=400
}

# Create the main converter script
create_converter_script() {
    print_step "Creating converter script..."
    mkdir -p "$INSTALL_DIR"

    cat > "$INSTALL_DIR/media-converter" << 'EOL'
#!/usr/bin/env bash
set -euo pipefail
generate_output_file() {
    local input_file="$1"
    local output_format="$2"
    local base_name output_dir output_file
    base_name=$(basename "$input_file" | sed 's/\.[^.]*$//')
    output_dir=$(dirname "$input_file")
    output_file="$output_dir/${base_name}_converted.${output_format}"
    local counter=1
    while [[ -f "$output_file" ]]; do
        output_file="$output_dir/${base_name}_converted_${counter}.${output_format}"
        ((counter++))
    done
    echo "$output_file"
}
generate_multi_output_file() {
    local input_file="$1"
    local output_format="$2"
    local base_name output_dir output_file
    base_name=$(basename "$input_file" | sed 's/\.[^.]*$//')
    output_dir=$(dirname "$input_file")
    output_file="$output_dir/${base_name}_converted_%03d.${output_format}"
    local counter=1
    while [[ -f "${output_file//%03d/001}" ]]; do
        output_file="$output_dir/${base_name}_converted_${counter}_%03d.${output_format}"
        ((counter++))
    done
    echo "$output_file"
}
get_duration() {
    local file="$1"
    local duration
    duration=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$file" 2>/dev/null)
    if [[ -n "$duration" && "$duration" != "N/A" ]]; then
        echo "${duration%.*}"
    else
        echo "0"
    fi
}
check_media_type() {
    local file="$1"
    local extension="${file##*.}"
    extension=$(echo "$extension" | tr '[:upper:]' '[:lower:]')
    case "$extension" in
        pdf|docx|odt|rtf|txt) echo "document"; return ;;
        srt|ass) echo "subtitle"; return ;;
        zip|tar) echo "archive"; return ;;
        tar.gz) echo "archive"; return ;;
        tar.bz2) echo "archive"; return ;;
    esac
    local codec_name
    codec_name=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$file" 2>/dev/null)
    case "$codec_name" in
        mjpeg|png|webp|gif|tiff|bmp|heif|ico)
            echo "image"
            ;;
        *)
            local video_streams=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$file" 2>/dev/null | grep -c "video" || true)
            local audio_streams=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$file" 2>/dev/null | grep -c "audio" || true)
            if [[ $video_streams -gt 0 ]]; then
                echo "video"
            elif [[ $audio_streams -gt 0 ]]; then
                echo "audio"
            else
                echo "invalid"
            fi
            ;;
    esac
}
extract_archive() {
    local archive_file="$1"
    local temp_dir="$2"
    local extension="${archive_file##*.}"
    extension=$(echo "$extension" | tr '[:upper:]' '[:lower:]')
    local media_files=()
    case "$extension" in
        zip)
            unzip -q "$archive_file" -d "$temp_dir" || {
                zenity --error --text="Failed to extract ZIP archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        tar)
            tar -xf "$archive_file" -C "$temp_dir" || {
                zenity --error --text="Failed to extract TAR archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        tar.gz)
            tar -xzf "$archive_file" -C "$temp_dir" || {
                zenity --error --text="Failed to extract TAR.GZ archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        tar.bz2)
            tar -xjf "$archive_file" -C "$temp_dir" || {
                zenity --error --text="Failed to extract TAR.BZ2 archive: $(basename "$archive_file")" --width=400
                return 1
            }
            ;;
        *)
            zenity --error --text="Unsupported archive format: $extension" --width=300
            return 1
            ;;
    esac
    while IFS= read -r -d '' file; do
        local file_type
        file_type=$(check_media_type "$file")
        if [[ "$file_type" != "invalid" && "$file_type" != "archive" ]]; then
            media_files+=("$file")
        fi
    done < <(find "$temp_dir" -type f -print0)
    echo "${media_files[@]}"
}
convert_document() {
    local input_file="$1"
    local output_format="$2"
    local output_file="$3"
    local is_image_output="$4"
    if [[ "$is_image_output" == "true" ]]; then
        local temp_pdf
        temp_pdf=$(mktemp --suffix=.pdf)
        if [[ "${input_file##*.}" != "pdf" ]]; then
            unoconv -f pdf -o "$temp_pdf" "$input_file" || {
                soffice --headless --convert-to pdf --outdir "$(dirname "$temp_pdf")" "$input_file" >/dev/null 2>&1 || {
                    zenity --error --text="Failed to convert $(basename "$input_file") to PDF" --width=400
                    rm -f "$temp_pdf"
                    return 1
                }
                mv "$(dirname "$temp_pdf")/$(basename "$input_file" | sed 's/\.[^.]*$//').pdf" "$temp_pdf"
            }
        else
            cp "$input_file" "$temp_pdf"
        fi
        echo "$temp_pdf"
        return 0
    else
        unoconv -f "$output_format" -o "$output_file" "$input_file" || {
            soffice --headless --convert-to "$output_format" --outdir "$(dirname "$output_file")" "$input_file" >/dev/null 2>&1 || {
                zenity --error --text="Failed to convert $(basename "$input_file") to $output_format" --width=400
                return 1
            }
            mv "$(dirname "$output_file")/$(basename "$input_file" | sed 's/\.[^.]*$//').$output_format" "$output_file"
        }
        return 0
    fi
}
get_conversion_opts() {
    local output_format="$1"
    case "$output_format" in
        mp3) echo "-c:a libmp3lame -q:a 2" ;;
        aac) echo "-c:a aac -b:a 192k" ;;
        flac) echo "-c:a flac" ;;
        ogg) echo "-c:a libvorbis -q:a 4" ;;
        wav) echo "-c:a pcm_s16le" ;;
        m4a) echo "-c:a aac -b:a 192k" ;;
        opus) echo "-c:a libopus -b:a 128k" ;;
        wma) echo "-c:a wmav2 -b:a 128k" ;;
        alac) echo "-c:a alac" ;;
        ac3) echo "-c:a ac3 -b:a 256k" ;;
        amr) echo "-c:a amr_nb -b:a 12.2k" ;;
        aiff) echo "-c:a pcm_s16le -f aiff" ;;
        mp4) echo "-c:v libx264 -crf 23 -preset medium -c:a aac -b:a 192k" ;;
        mkv) echo "-c:v libx264 -crf 23 -c:a aac -b:a 192k" ;;
        avi) echo "-c:v mpeg4 -c:a mp3 -q:a 2" ;;
        webm) echo "-c:v libvpx-vp9 -crf 30 -b:v 0 -c:a libopus -b:a 128k" ;;
        mov) echo "-c:v libx264 -crf 23 -c:a aac -b:a 192k" ;;
        flv) echo "-c:v flv1 -c:a mp3 -b:a 128k" ;;
        wmv) echo "-c:v wmv2 -c:a wmav2 -b:a 128k" ;;
        m4v) echo "-c:v libx264 -crf 23 -c:a aac -b:a 192k" ;;
        3gp) echo "-c:v h263 -c:a amr_nb -b:a 12.2k" ;;
        ts) echo "-c:v mpeg2video -c:a mp2 -b:a 192k" ;;
        ogv) echo "-c:v libtheora -c:a libvorbis -q:v 7 -q:a 4" ;;
        vob) echo "-c:v mpeg2video -c:a ac3 -b:a 192k" ;;
        jpg) echo "-c:v mjpeg -q:v 2" ;;
        png) echo "-c:v png" ;;
        webp) echo "-c:v webp -quality 80" ;;
        gif) echo "-c:v gif" ;;
        tiff) echo "-c:v tiff" ;;
        bmp) echo "-c:v bmp" ;;
        heif) echo "-c:v libheif" ;;
        ico) echo "-c:v ico" ;;
        srt|ass) echo "" ;;
        *) echo "" ;;
    esac
}
convert_file() {
    local input_file="$1"
    local output_format="$2"
    local progress_file="$3"
    local current_file="$4"
    local total_files="$5"
    local pdf_mode="$6"
    local file_type
    file_type=$(check_media_type "$input_file")
    if [[ "$file_type" == "invalid" ]]; then
        zenity --error --text="Not a valid media file: $(basename "$input_file")" --width=400
        return 1
    fi
    if [[ "$file_type" == "archive" ]]; then
        local temp_dir
        temp_dir=$(mktemp -d)
        local media_files
        media_files=($(extract_archive "$input_file" "$temp_dir"))
        if [[ ${#media_files[@]} -eq 0 ]]; then
            zenity --error --text="No supported media files found in archive: $(basename "$input_file")" --width=400
            rm -rf "$temp_dir"
            return 1
        fi
        local success_count=0
        local failed_files=()
        for ((i=0; i<${#media_files[@]}; i++)); do
            local media_file="${media_files[i]}"
            local sub_progress_file="$progress_file.$i"
            if convert_file "$media_file" "$output_format" "$sub_progress_file" "$current_file" "$total_files" "$pdf_mode"; then
                ((success_count++))
            else
                failed_files+=("$(basename "$media_file")")
            fi
        done
        rm -rf "$temp_dir"
        if [[ ${#failed_files[@]} -eq 0 ]]; then
            return 0
        else
            zenity --error --text="Archive conversion failed for some files in $(basename "$input_file"):\n${failed_files[*]}" --width=400
            return 1
        fi
    fi
    local output_type
    case "$output_format" in
        mp3|aac|wav|flac|ogg|m4a|opus|wma|alac|ac3|amr|aiff) output_type="audio" ;;
        mp4|mkv|avi|webm|mov|flv|wmv|m4v|3gp|ts|ogv|vob) output_type="video" ;;
        jpg|png|webp|gif|tiff|bmp|heif|ico) output_type="image" ;;
        srt|ass) output_type="subtitle" ;;
        pdf|docx|odt|rtf|txt) output_type="document" ;;
        *) 
            zenity --error --text="Unsupported format: $output_format" --width=300
            return 1
            ;;
    esac
    if [[ "$output_type" == "audio" && "$file_type" != "audio" && "$file_type" != "video" ]]; then
        zenity --error --text="Cannot convert $file_type to audio: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$output_type" == "video" && "$file_type" != "video" && "$file_type" != "subtitle" ]]; then
        zenity --error --text="Cannot convert $file_type to video: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$output_type" == "image" && "$file_type" != "image" && "$file_type" != "document" ]]; then
        zenity --error --text="Can only convert images or documents to image formats: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$output_type" == "document" && "$file_type" != "document" ]]; then
        zenity --error --text="Can only convert documents to document formats: $(basename "$input_file")" --width=400
        return 1
    elif [[ "$file_type" == "subtitle" && "$output_type" != "subtitle" && "$output_type" != "video" ]]; then
        zenity --error --text="Can only convert subtitles to subtitle or video formats: $(basename "$input_file")" --width=400
        return 1
    fi
    local output_file
    if [[ "$output_type" == "image" && "$file_type" == "document" && "$pdf_mode" == "multi" && "$output_format" != "gif" ]]; then
        output_file=$(generate_multi_output_file "$input_file" "$output_format")
    else
        output_file=$(generate_output_file "$input_file" "$output_format")
    fi
    if [[ "$output_type" == "document" ]]; then
        convert_document "$input_file" "$output_format" "$output_file" "false" || {
            return 1
        }
        echo "# Completed file $current_file of $total_files: $(basename "$input_file")"
        return 0
    fi
    local actual_input_file="$input_file"
    if [[ "$file_type" == "document" && "$output_type" == "image" ]]; then
        actual_input_file=$(convert_document "$input_file" "pdf" "" "true") || {
            return 1
        }
    fi
    local conversion_opts
    conversion_opts=$(get_conversion_opts "$output_format")
    local duration=0
    if [[ "$file_type" == "video" || "$file_type" == "audio" ]]; then
        duration=$(get_duration "$actual_input_file")
    fi
    local ffmpeg_args=()
    if [[ "$file_type" == "document" && "$output_type" == "image" ]]; then
        if [[ "$pdf_mode" == "single" ]]; then
            ffmpeg_args=(-i "$actual_input_file" -vframes 1 "$output_file")
        else
            ffmpeg_args=(-i "$actual_input_file" "$output_file")
        fi
    elif [[ "$file_type" == "image" && "$output_type" == "image" ]]; then
        ffmpeg_args=(-i "$actual_input_file" $conversion_opts "$output_file")
    elif [[ "$file_type" == "document" && "${actual_input_file##*.}" == "txt" && "$output_type" == "image" ]]; then
        ffmpeg_args=(-f lavfi -i "color=c=white:s=1280x720" -vf "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile='$actual_input_file':fontcolor=black:fontsize=24:x=10:y=10" -frames:v 1 "$output_file")
    elif [[ "$file_type" == "video" && "$output_type" == "audio" ]]; then
        ffmpeg_args=(-i "$actual_input_file" -vn $conversion_opts "$output_file")
    elif [[ "$file_type" == "subtitle" && "$output_type" == "video" ]]; then
        ffmpeg_args=(-i "$actual_input_file" -vf "subtitles='$actual_input_file'" "$output_file")
    elif [[ "$file_type" == "subtitle" && "$output_type" == "subtitle" ]]; then
        ffmpeg_args=(-i "$actual_input_file" "$output_file")
    else
        ffmpeg_args=(-i "$actual_input_file" $conversion_opts "$output_file")
    fi
    (
        ffmpeg "${ffmpeg_args[@]}" -progress "$progress_file" 2>/dev/null &
        local ffmpeg_pid=$!
        while kill -0 $ffmpeg_pid 2>/dev/null; do
            if [[ -f "$progress_file" && "$file_type" != "image" && "$file_type" != "document" && "$file_type" != "subtitle" ]]; then
                local current_time
                current_time=$(grep -oP 'out_time=\K[0-9:.]*' "$progress_file" 2>/dev/null | tail -n1)
                if [[ -n "$current_time" && $duration -gt 0 ]]; then
                    local current_seconds
                    current_seconds=$(echo "$current_time" | awk -F: '{print ($1 * 3600) + ($2 * 60) + $3}')
                    local percentage
                    percentage=$(( (current_seconds * 100) / duration ))
                    if [[ $percentage -le 100 ]]; then
                        echo "$percentage"
                        echo "# File $current_file of $total_files: $(basename "$input_file") ($percentage%)"
                    fi
                else
                    echo "# Processing file $current_file of $total_files: $(basename "$input_file")"
                fi
            else
                echo "# Processing file $current_file of $total_files: $(basename "$input_file")"
            fi
            sleep 1
        done
        wait $ffmpeg_pid
        local ffmpeg_exit_status=$?
        if [[ $ffmpeg_exit_status -eq 0 && (-f "$output_file" || -f "${output_file//%03d/001}") && (-s "$output_file" || -s "${output_file//%03d/001}") ]]; then
            echo "100"
            echo "# Completed file $current_file of $total_files: $(basename "$input_file")"
            [[ "$actual_input_file" != "$input_file" ]] && rm -f "$actual_input_file"
            return 0
        else
            echo "# Conversion failed for file $current_file of $total_files: $(basename "$input_file")"
            [[ "$actual_input_file" != "$input_file" ]] && rm -f "$actual_input_file"
            return 1
        fi
    ) || {
        pkill -P $$ ffmpeg
        [[ "$actual_input_file" != "$input_file" ]] && rm -f "$actual_input_file"
        return 1
    }
}
main() {
    local output_format="$1"
    shift
    local input_files=("$@")
    local total_files=${#input_files[@]}
    local pdf_mode="single"
    if [[ $total_files -eq 0 ]]; then
        zenity --error --text="No input files provided" --width=300
        exit 1
    fi
    if [[ "$output_format" == "jpg" || "$output_format" == "png" || "$output_format" == "webp" || "$output_format" == "gif" || "$output_format" == "tiff" || "$output_format" == "bmp" || "$output_format" == "heif" || "$output_format" == "ico" ]]; then
        for input_file in "${input_files[@]}"; do
            if [[ $(check_media_type "$input_file") == "document" ]]; then
                pdf_mode=$(zenity --list --title="Document Conversion Mode" --text="Choose document conversion mode:" --column="Mode" --width=300 --height=200 \
                    "Single Page (First)" \
                    "All Pages (Separate Images)" \
                    "All Pages (Animated GIF)" || echo "single")
                case "$pdf_mode" in
                    "All Pages (Separate Images)") pdf_mode="multi" ;;
                    "All Pages (Animated GIF)") pdf_mode="multi"; output_format="gif" ;;
                    *) pdf_mode="single" ;;
                esac
                break
            fi
        done
    fi
    local temp_dir
    temp_dir=$(mktemp -d)
    trap 'rm -rf "$temp_dir"' EXIT
    (
        local success_count=0
        local failed_files=()
        for ((i=0; i<${#input_files[@]}; i++)); do
            local input_file="${input_files[i]}"
            local progress_file="$temp_dir/progress_$i"
            local current_file=$((i + 1))
            if convert_file "$input_file" "$output_format" "$progress_file" "$current_file" "$total_files" "$pdf_mode"; then
                ((success_count++))
            else
                failed_files+=("$(basename "$input_file")")
            fi
        done
        if [[ ${#failed_files[@]} -eq 0 ]]; then
            echo "# All $total_files files converted successfully."
        else
            local failed_msg="# Converted $success_count of $total_files files.\n\nFailed files:\n"
            printf -v failed_msg "$failed_msg%s\n" "${failed_files[@]}"
            echo "$failed_msg"
        fi
    ) | zenity --progress \
        --title="Converting Media" \
        --text="Starting conversion..." \
        --percentage=0 \
        --auto-close \
        --width=400
}
main "$@"
EOL

    chmod +x "$INSTALL_DIR/media-converter"
    print_success "Converter script created"
}

# Create Nautilus context menu scripts
create_nautilus_scripts() {
    print_step "Creating Nautilus scripts..."
    
    mkdir -p "$NAUTILUS_SCRIPTS_DIR/Media Converter/Audio"
    for format in "${!AUDIO_FORMATS[@]}"; do
        script_name="$NAUTILUS_SCRIPTS_DIR/Media Converter/Audio/To ${format^^} (${AUDIO_FORMATS[$format]})"
        cat > "$script_name" << EOL
#!/bin/bash
"$INSTALL_DIR/media-converter" "$format" "\$@"
EOL
        chmod +x "$script_name"
    done

    mkdir -p "$NAUTILUS_SCRIPTS_DIR/Media Converter/Video"
    for format in "${!VIDEO_FORMATS[@]}"; do
        script_name="$NAUTILUS_SCRIPTS_DIR/Media Converter/Video/To ${format^^} (${VIDEO_FORMATS[$format]})"
        cat > "$script_name" << EOL
#!/bin/bash
"$INSTALL_DIR/media-converter" "$format" "\$@"
EOL
        chmod +x "$script_name"
    done

    mkdir -p "$NAUTILUS_SCRIPTS_DIR/Media Converter/Image"
    for format in "${!IMAGE_FORMATS[@]}"; do
        script_name="$NAUTILUS_SCRIPTS_DIR/Media Converter/Image/To ${format^^} (${IMAGE_FORMATS[$format]})"
        cat > "$script_name" << EOL
#!/bin/bash
"$INSTALL_DIR/media-converter" "$format" "\$@"
EOL
        chmod +x "$script_name"
    done

    mkdir -p "$NAUTILUS_SCRIPTS_DIR/Media Converter/Document"
    for format in "${!DOCUMENT_FORMATS[@]}"; do
        script_name="$NAUTILUS_SCRIPTS_DIR/Media Converter/Document/To ${format^^} (${DOCUMENT_FORMATS[$format]})"
        cat > "$script_name" << EOL
#!/bin/bash
"$INSTALL_DIR/media-converter" "$format" "\$@"
EOL
        chmod +x "$script_name"
    done

    mkdir -p "$NAUTILUS_SCRIPTS_DIR/Media Converter/Subtitle"
    for format in "${!SUBTITLE_FORMATS[@]}"; do
        script_name="$NAUTILUS_SCRIPTS_DIR/Media Converter/Subtitle/To ${format^^} (${SUBTITLE_FORMATS[$format]})"
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
    echo "Restart your file manager to see the new scripts in the context menu -> Scripts -> Media Converter -> [Audio/Video/Image/Document/Subtitle]."
    echo "Documents (.pdf, .docx, .odt, .rtf, .txt) can be converted to other document formats under 'Document' or to images under 'Image'."
    echo "Archives (.zip, .tar, etc.) are processed under the appropriate submenu based on their contents."
}

main
