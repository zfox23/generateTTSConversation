"""Generate Polly TTS Speech from Input Text"""
from boto3 import Session
from botocore.exceptions import BotoCoreError, ClientError
from contextlib import closing
from pydub import AudioSegment
import os
import sys
import getopt
import datetime


def main(argv):
    inputFilePath = ''
    outputDir = os.getcwd()
    helpText = 'generateTTSConversation.py -i <inputFilePath> [-o <outputDirectory>]'
    separateOutputFilesByVoice = False
    try:
        opts, args = getopt.getopt(argv, "shoi:", ["ifile=", "odir="])
    except getopt.GetoptError:
        print(helpText)
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print(helpText)
            sys.exit()
        elif opt in ("-i", "--ifile"):
            inputFilePath = arg
        elif opt in ("-o", "--odir"):
            outputDir = os.path.abspath(arg)
            print("Using custom outputDir: " + outputDir)
        elif opt in ("-s"):
            separateOutputFilesByVoice = True

    # Create a client using the credentials and region defined in the [default]
    # section of the AWS credentials file (~/.aws/credentials).
    session = Session(profile_name="default")
    polly = session.client("polly")

    numVoiceLines = 0
    allOutputVoiceLines = []
    allVoiceIDs = []

    with open(inputFilePath) as fp:
        textFileLines = fp.read().splitlines()

    readingName = True
    for line in textFileLines:
        if readingName:
            numVoiceLines += 1
            currentVoiceID = line
            if currentVoiceID not in allVoiceIDs:
                allVoiceIDs.append(currentVoiceID)
            readingName = False
            continue
        else:
            nextText = line
            nextText = ("<speak>" + nextText + "</speak>")
            readingName = True

        try:
            # Request speech synthesis
            response = polly.synthesize_speech(
                Text=nextText, TextType="ssml", OutputFormat="mp3", VoiceId=currentVoiceID)
        except (BotoCoreError, ClientError) as error:
            # The service returned an error, exit gracefully
            print(error)
            sys.exit(-1)

        # Access the audio stream from the response
        if "AudioStream" in response:
            # Note: Closing the stream is important because the service throttles on the
            # number of parallel connections. Here we are using contextlib.closing to
            # ensure the close method of the stream object will be called automatically
            # at the end of the with statement's scope.
            with closing(response["AudioStream"]) as stream:
                currentVoiceFilePath = os.path.join(
                    outputDir, "tempSpeech" + currentVoiceID + str(numVoiceLines) + ".mp3")
                allOutputVoiceLines.append(
                    dict([("path", currentVoiceFilePath), ("voiceID", currentVoiceID)]))

                try:
                    # Open a file for writing the output as a binary stream
                    with open(currentVoiceFilePath, "wb") as file:
                        file.write(stream.read())
                except IOError as error:
                    # Could not write to file, exit gracefully
                    print(error)
                    sys.exit(-1)

        else:
            # The response didn't contain audio data, exit gracefully
            print("Could not stream audio.")
            sys.exit(-1)

    outputSegments = {}
    for id in allVoiceIDs:
        outputSegments[id] = AudioSegment.silent(duration=0)

    runningTotalDuration = 0
    for currentSpokenLine in allOutputVoiceLines:
        currentSpeakerID = currentSpokenLine["voiceID"]
        currentMP3Path = currentSpokenLine["path"]

        print("Running total audio duration: " +
                str(runningTotalDuration))
        print("Current speaker: " + currentSpeakerID)

        currentSegment = AudioSegment.from_mp3(currentMP3Path)
        currentSegmentLength = len(currentSegment)

        for id in allVoiceIDs:
            if currentSpeakerID == id:
                print(id + ": Appending segment from " +
                        currentMP3Path + "...")
                outputSegments[id] += currentSegment
            else:
                print(id + ": Appending " +
                        str(currentSegmentLength) + "ms of silence to AudioSegment...")
                outputSegments[id] += AudioSegment.silent(
                    duration=currentSegmentLength)
            # Add a little extra silence at the end of each clip for more natural-sounding conversation.
            outputSegments[id] += AudioSegment.silent(
                    duration=450)

        print("")
        runningTotalDuration += currentSegmentLength

    # Export logic
    combinedSegment = AudioSegment.silent(duration=0)
    lastSegment = False
    now = datetime.datetime.now()
    now = now.strftime('%Y-%m-%d_%H-%M-%S')
    for voiceID, segment in outputSegments.items():
        outputFilePath = os.path.join(
            outputDir, now + "_" + voiceID + ".mp3")
        if separateOutputFilesByVoice:
            print("Exporting TTS audio for " + voiceID + " of length " +
                    str(len(segment)) + "ms to an MP3 at \"" + outputFilePath + "\"")
            segment.export(outputFilePath, format="mp3")
        if lastSegment:
            combinedSegment = lastSegment.overlay(segment)
            lastSegment = combinedSegment
        else:
            lastSegment = segment
            
    outputFilePath = os.path.join(outputDir, now + "_Combined.mp3")
    print("Exporting TTS audio to a single file at \"" +
            outputFilePath + "\"")
    combinedSegment.export(outputFilePath, format="mp3")    

    for currentSpokenLine in allOutputVoiceLines:
        voiceFilePath = currentSpokenLine["path"]
        os.remove(voiceFilePath)

if __name__ == "__main__":
    main(sys.argv[1:])
