const Logger = require('./logger.js');

const express = require('express');
const bodyParser = require('body-parser');

module.exports.app;
module.exports.server;

module.exports.init = async function init(port) {
    module.exports.app = express();
    // Incase i need to use websockets in the future
    module.exports.server = require('http').createServer(module.exports.app); 

    Logger.info('Server Settup');

    try {
        module.exports.app.use(bodyParser.json());
        module.exports.app.use(bodyParser.urlencoded({ extended: true }));
        module.exports.app.listen(port);
    } catch (e) {
        Logger.panic(`Could not open a connection on port ${port}, maybe the port is populated or permissions are not met`);
    }
    
    Logger.info(`HTTP service is listening at port ${port}`);

}
