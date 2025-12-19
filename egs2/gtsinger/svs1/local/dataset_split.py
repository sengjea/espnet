import argparse
import ast
import json
import os
import shutil

import textgrid

from espnet2.fileio.score_scp import SingingScoreWriter, XMLReader

def train_check(relativepath):
    return any([m in relativepath for m in [
      "All I Ask",
      "Always Remember Us This Way",
      "Enchanted",
      "I Knew You Were Trouble",
      "Long Live",
      "Million Reasons",
      "Rolling in the Deep",
      "Stay",
      "Unconditionally",
      "You Belong With Me"
    ]]) and "Breathy" in relativepath and "Control_Group" in relativepath


def dev_check(relativepath):
    return any([m in relativepath for m in [
      "Someone Like You",
    ]]) and "Breathy" in relativepath and "Control_Group" in relativepath


def test_check(relativepath):
    return any([m in relativepath for m in [
      "Shallow",
    ]]) and "Breathy" in relativepath and "Control_Group" in relativepath


def pack_zero(string, size=20):
    if len(string) < size:
        string = "0" * (size - len(string)) + string
    return string


def makedir(data_url):
    if os.path.exists(data_url):
        shutil.rmtree(data_url)

    os.makedirs(data_url)

def read_phoneme_textgrid(filepath):
    tg = textgrid.TextGrid.fromFile(filepath)
    for tier in tg.tiers:
      if tier.name == "phone":
        for interval in tier:
          yield interval.minTime, interval.maxTime, interval.mark.strip("<>")


def process_pho_info(phoneme_iter):
    label_info = []
    pho_info = []
    for start_time, end_time, label in phoneme_iter:
        label_info.append(f"{start_time} {end_time} {label}")
        pho_info.append(label)

    return " ".join(label_info), " ".join(pho_info)


def process_score_info(notes, phoneme_iter):
    score_notes = []
    current_phoneme = None
    for note in notes:
        if note.lyric == "—":
            score_notes[-1][1] = note.et
        if note.lyric == "P":
            note.lyric = "AP"
        if note.lyric != "—":
            phonemes = []
            while True:
              if current_phoneme == None:
                current_phoneme = next(phoneme_iter)
                print(current_phoneme)
              if current_phoneme[1] > note.et:
                break
              else:
                phonemes.append(current_phoneme[2])
                current_phoneme = None
            score = [
                    note.st,
                    note.et,
                    note.lyric,
                    note.midi,
                    "_".join(phonemes),
                ]
            print(score)
            score_notes.append(score)

    return score_notes


def process_json_to_pho_score(basepath, tempo, notes):
    parts = basepath.split("/")
    textgrid_file = basepath + ".TextGrid"
    label_info, pho_info = process_pho_info(read_phoneme_textgrid(textgrid_file))

    score_notes = process_score_info(notes, read_phoneme_textgrid(textgrid_file))

    return (
        label_info,
        pho_info,
        dict(
            tempo=tempo,
            item_list=["st", "et", "lyric", "midi", "phn"],
            note=score_notes,
        ),
    )


def process_subset(src_data, subset, filter_func, fs, wav_dump, score_dump):
    makedir(subset)
    wavscp = open(os.path.join(subset, "wav.scp"), "w", encoding="utf-8")
    utt2spk = open(os.path.join(subset, "utt2spk"), "w", encoding="utf-8")
    label_scp = open(os.path.join(subset, "label"), "w", encoding="utf-8")
    xml_scp = open(os.path.join(subset, "xml.scp"), "w", encoding="utf-8")

    for root, dirs, files in os.walk(src_data):
        if not dirs:
            for file in files:
                filepath = os.path.join(root, file)
                relativepath = os.path.relpath(filepath, start=src_data)
                basepath = os.path.splitext(filepath)[0]
                speaker = relativepath.split("/")[1]
                if not relativepath.endswith("wav") or ".cache" in relativepath:
                  continue
                if not filter_func(relativepath):
                  continue

                utt_id = relativepath.replace("/","_").replace(" ", "_")

                wavscp.write("{} {}\n".format(utt_id, filepath))
                utt2spk.write("{} {}\n".format(utt_id, speaker))
                xml_scp.write(
                    "{} {}\n".format(
                        utt_id, basepath + ".musicxml"
                    )
                )

    reader = XMLReader(os.path.join(subset, "xml.scp"))
    score_writer = SingingScoreWriter(score_dump, os.path.join(subset, "score.scp"))
    text = open(os.path.join(subset, "text"), "w", encoding="utf-8")
    for utt_id in reader.keys():
        print(f"Processing {utt_id}")
        musicxml = reader.get_path(utt_id)
        tempo, notes = reader[utt_id]
        basepath = os.path.splitext(musicxml)[0]
        label_info, pho_info, score_info = process_json_to_pho_score(
          basepath, tempo, notes
        )

        label_scp.write("{} {}\n".format(utt_id, label_info))
        text.write("{} {}\n".format(utt_id, pho_info))
        score_writer[utt_id] = score_info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare Data for Oniku Database")
    parser.add_argument("src_data", type=str, help="source data directory")
    parser.add_argument("train", type=str, help="train set")
    parser.add_argument("dev", type=str, help="development set")
    parser.add_argument("test", type=str, help="test set")
    parser.add_argument("--fs", type=int, help="frame rate (Hz)")
    parser.add_argument(
        "--wav_dump", type=str, default="wav_dump", help="wav dump directory"
    )
    parser.add_argument(
        "--score_dump", type=str, default="score_dump", help="score dump directory"
    )

    args = parser.parse_args()

    if not os.path.exists(args.wav_dump):
        os.makedirs(args.wav_dump)

    process_subset(
        args.src_data, args.train, train_check, args.fs, args.wav_dump, args.score_dump
    )
    process_subset(
        args.src_data, args.dev, dev_check, args.fs, args.wav_dump, args.score_dump
    )
    process_subset(
        args.src_data, args.test, test_check, args.fs, args.wav_dump, args.score_dump
    )
