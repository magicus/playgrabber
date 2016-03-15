#!/bin/bash

NUM_SUBTITLES=$(ls -1 *.srt 2> /dev/null | wc -l)
if [[ $NUM_SUBTITLES -eq 0 ]]; then
  echo "No subtitle files found. Aborting" > /dev/stderr
  exit 1
fi

BASE_SHOW_NAME="$(ls *.srt | sed -e 's/\([^.]*\).*/\1/' | head -1)"
# tr '[:upper:]' does not handle localized unicode :-(
UPPERCASE_SHOW_NAME="$(echo $BASE_SHOW_NAME | sed 's/.*/\U&/')"

if [[ ! -f title-suggestions.txt ]]; then
  grep -H -A1 middle *.srt | grep -v -e '--' -e '[tT]extning' -e "$UPPERCASE_SHOW_NAME" | awk -F 'srt-' '{ print $1 "srt-" substr($2,1,1) tolower(substr($2,2)) }' > title-suggestions.txt
  echo "Processed $NUM_SUBTITLES subtitles for $BASE_SHOW_NAME"
  echo "Please verify title-suggestions.txt and run this script again"
  cat title-suggestions.txt
else
  sed -e 's/\(.*\.E[0-9][0-9]*\.\)\(.*\)\.srt-\(.*\)\r$/mv "\1\2.mp4" "\1\3.mp4"/' title-suggestions.txt > title-script.sh
  sed -e 's/\(.*\.E[0-9][0-9]*\.\)\(.*\)\.srt-\(.*\)\r$/mv "\1\2.srt" "\1\3.srt"/' title-suggestions.txt >> title-script.sh
  echo "Renaming files for $BASE_SHOW_NAME"
  . title-script.sh
  rm title-script.sh
  rm title-suggestions.txt
  echo "Done"
fi
