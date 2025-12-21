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

def phoneme_iterator(filepath):
    tg = textgrid.TextGrid.fromFile(filepath)
    yield from next((t for t in tg.tiers if t.name == "phone"))


def process_pho_info(phoneme_iter):
    label_info = []
    pho_info = []
    for interval in phoneme_iter:
      label = interval.mark.strip("<>")
      label_info.append(f"{interval.minTime} {interval.maxTime} {label}")
      pho_info.append(label)

    return " ".join(label_info), " ".join(pho_info)

def word_phoneme_iterator(filepath):
    tg = textgrid.TextGrid.fromFile(filepath)
    word_iterator = iter(next((t for t in tg.tiers if t.name == "word")).intervals)
    phoneme_iterator = iter(next((t for t in tg.tiers if t.name == "phone")).intervals)
    word = next(word_iterator)
    for phoneme in phoneme_iterator:
      yield word.mark.strip("<>"), phoneme.mark.strip("<>"), phoneme.maxTime
      if phoneme.maxTime >= word.maxTime:
        word = next(word_iterator, None)

def process_score_info(notes, word_phoneme_iter):
    score_notes = []
    for note in notes:
      phonemes = []
      word, phoneme, maxTime = next(word_phoneme_iter, (None, None, note.et))
      if phoneme:
        phonemes.append(phoneme)
      while maxTime < note.et:
        word, phoneme, maxTime = next(word_phoneme_iter, (word, None, note.et))
        if phoneme:
          phonemes.append(phoneme)
      score_notes.append([
                    note.st,
                    note.et,
                    word if word != "P" else "AP",
                    note.midi,
                    "_".join(phonemes),
                ])

    return score_notes


def process_json_to_pho_score(basepath, tempo, notes):
    parts = basepath.split("/")
    textgrid_file = basepath + ".TextGrid"
    label_info, pho_info = process_pho_info(phoneme_iterator(textgrid_file))

    score_notes = process_score_info(notes, word_phoneme_iterator(textgrid_file))

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
                utt2spk.write("{} {}\n".format(utt_id, utt_id))
                xml_scp.write(
                    "{} {}\n".format(
                        utt_id, basepath + ".musicxml"
                    )
                )
    xml_scp.close()
    reader = XMLReader(os.path.join(subset, "xml.scp"))
    score_writer = SingingScoreWriter(score_dump, os.path.join(subset, "score.scp"))
    text = open(os.path.join(subset, "text"), "w", encoding="utf-8")
    for utt_id in reader.keys():
        musicxml = reader.get_path(utt_id)
        tempo, notes = reader[utt_id]
        basepath = os.path.splitext(musicxml)[0]
        try:
          label_info, pho_info, score_info = process_json_to_pho_score(
            basepath, tempo, notes
          )

          label_scp.write("{} {}\n".format(utt_id, label_info))
          text.write("{} {}\n".format(utt_id, pho_info))
          score_writer[utt_id] = score_info
        except Exception as e:
          print(f"Unable to process {utt_id}: {e}")


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
    print("processing train")
    process_subset(
        args.src_data, args.train, train_check, args.fs, args.wav_dump, args.score_dump
    )
    print("processing dev")
    process_subset(
        args.src_data, args.dev, dev_check, args.fs, args.wav_dump, args.score_dump
    )
    print("processing test")
    process_subset(
        args.src_data, args.test, test_check, args.fs, args.wav_dump, args.score_dump
    )
