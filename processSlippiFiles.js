const { SlippiGame } = require("@slippi/slippi-js");

args = process.argv.slice(2);

retObj = {}
for (let g=0; g < args.length; g++) {
    try {
        const game = new SlippiGame(args[g]);

        // Get game settings – stage, characters, etc
        const settings = game.getSettings();
        // console.log(settings);

        // Get metadata - start time, platform played on, etc
        const metadata = game.getMetadata();
        // console.log(metadata);

        // Get computed stats - openings / kill, conversions, etc
        // const stats = game.getStats();
        // console.log(stats);

        // // Get frames – animation state, inputs, etc
        // // This is used to compute your own stats or get more frame-specific info (advanced)
        // const frames = game.getFrames();
        // console.log(frames[0].players); // Print frame when timer starts counting down
        var fname = args[g].substring(args[g].lastIndexOf('\\')+1);
        var printoutObj = {};
        printoutObj['timestamp'] = metadata.startAt;
        printoutObj['duration'] = metadata.lastFrame;
        printoutObj['stage'] = settings.stageId;

        for (let i = 0; i < 4; i++) {
            try {
                printoutObj[`p${i}_char`] = Object.keys(metadata.players[i].characters)[0];
                printoutObj[`p${i}_code`] = metadata.players[i].names.code;
                printoutObj[`p${i}_name`] = metadata.players[i].names.netplay;
            } catch (error) {
                printoutObj[`p${i}_char`] = '?';
                printoutObj[`p${i}_code`] = '?';
                printoutObj[`p${i}_name`] = '?';
            }
        }
        
        if (metadata.lastFrame > 300) {
            retObj[fname] = printoutObj;
        }
    } catch (error) {}
    
}
console.log(JSON.stringify(retObj));
