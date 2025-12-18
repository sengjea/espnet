import argparse
import ast
import json
import os
import shutil

import textgrid
from pypinyin import Style, pinyin
from pypinyin.style._utils import get_finals, get_initials

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

def process_pho_info(filepath):
    tg = textgrid.TextGrid.fromFile(filepath)
    phone_tier = None
    for tier in tg.tiers:
        if tier.name == "phone":
            phone_tier = tier
            break
    if phone_tier is None:
        raise ValueError("No 'phone' tier found in the TextGrid file.")
    label_info = []
    pho_info = []
    for interval in phone_tier:
        start_time = interval.minTime
        end_time = interval.maxTime
        label = interval.mark.strip()
        if "<" in label or ">" in label:
            label = label[1:-1]
        label_info.append(f"{start_time} {end_time} {label}")
        pho_info.append(label)

    return label_info, pho_info


def process_score_info(notes, label_pho_info, utt_id):
    score_notes = []
    phnes = []
    labelind = 0
    for i in range(len(notes)):
        if notes[i].lyric == "—":
            score_notes[-1][1] = notes[i].et
        if notes[i].lyric == "P":
            notes[i].lyric = "AP"
        if notes[i].lyric != "—":
            phonemes = []
            while True:
              if labelind >= len(label_pho_info):  # error
                exit(1)
              labelled_phoneme = label_pho_info[labelind]
              phoneme_end_time = labelled_phoneme.split(" ")[1]
              print(notes[i].et, phoneme_end_time)
              if phoneme_end_time > notes[i].et:
                break
              else:
                phonemes.append(labelled_phoneme.split(" ")[2])
            score_notes.append(
                [
                    notes[i].st,
                    notes[i].et,
                    notes[i].lyric,
                    notes[i].midi,
                    "_".join(phonemes),
                ]
            )
            phnes.extend(phonemes)

    return score_notes, phnes


def process_json_to_pho_score(utt_id, basepath, tempo, notes):
    parts = basepath.split("/")
    label_info, pho_info = process_pho_info(basepath + ".TextGrid")

    score_notes, phnes = process_score_info(notes, label_info, utt_id)

    if len(pho_info) != len(phnes):  # error
        exit(1)
    else:  # check score and label
        f = False
        for i in range(len(pho_info)):
            assert pho_info[i] == phnes[i]
            if pho_info[i] != phnes[i]:
                f = True

        if f is True:  # error
            exit(1)

    return (
        " ".join(label_info),
        " ".join(pho_info),
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
    musicxml = open(os.path.join(subset, "score.scp"), "w", encoding="utf-8")

    for root, dirs, files in os.walk(src_data):
        if not dirs:
            for file in files:
                filepath = os.path.join(root, file)
                relativepath = os.path.relpath(filepath, start=src_data)
                speaker = relativepath.split("/")[1]
                if not relativepath.endswith("wav") or ".cache" in relativepath:
                  continue
                if not filter_func(relativepath):
                  continue

                utt_id = relativepath.replace("/","_").replace(" ", "_")

                wavscp.write("{} {}\n".format(utt_id, filepath))
                utt2spk.write("{} {}\n".format(utt_id, speaker))
                musicxml.write(
                    "{} {}\n".format(
                        utt_id, os.path.splitext(filepath)[0] + ".musicxml"
                    )
                )

    reader = XMLReader(os.path.join(subset, "score.scp"))
    scorescp = open(os.path.join(subset, "score.scp"), "r", encoding="utf-8")
    score_writer = SingingScoreWriter(score_dump, os.path.join(subset, "score.scp.tmp"))
    text = open(os.path.join(subset, "text"), "w", encoding="utf-8")
    for xml_line in scorescp:
        xmlline = xml_line.strip().split(" ")
        utt_id = xmlline[0]
        musicxml = " ".join(xmlline[1:])
        tempo, notes = reader[utt_id]
        basepath = os.path.splitext(musicxml)[0]
        label_info, text_info, score_info = process_json_to_pho_score(
            utt_id, basepath, tempo, notes
        )

        label_scp.write("{} {}\n".format(utt_id, label_info))
        text.write("{} {}\n".format(utt_id, text_info))
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
