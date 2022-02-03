const { SlippiGame } = require("@slippi/slippi-js");

slp_file = process.argv[2];
const game = new SlippiGame(slp_file);

// Get metadata - start time, platform played on, etc
const metadata = game.getMetadata();
console.log(metadata.lastFrame);