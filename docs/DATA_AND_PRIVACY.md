# Data and privacy

## What stays on the computer

The application listens on 127.0.0.1 only. Each session uses a random token, and requests with a foreign Host header are refused. The interface loads no external scripts, fonts or images.

## What leaves the computer

During a real run, each question and its options are sent to the model provider you selected. Nothing else is sent. With a local OpenAI-compatible endpoint, nothing leaves the computer.

## API keys

Keys are held in memory for the run, are not written to disk, run metadata, logs or exports, and are cleared from the form when a run starts. This is covered by an automated test. Anyone with access to your unlocked computer session can still use a key you typed into the app, so use keys limited to this purpose.

## Item content

Do not import items that contain patient information or personal identifiers. The built-in benchmark contains no personal data.

## Stored files

Run folders contain model replies and metadata. They contain no keys. They can be deleted by removing the run folder.

## Not covered

The application is not code-signed. Operating system disk encryption and access control are the user's responsibility.
