const Logger = require('./logger.js');
const Server = require('./server.js');
const Website = require('./website.js');
const Middleware = require('./middlewares/middleware.js');
const Services = require('./servicehandle.js');

module.exports.main = async function() {
    Logger.init();
    Logger.SetLevel(Logger.VERBOSE_LOGS);

    Logger.info('Webservice starting up');

    await Server.init(80);

    await Middleware.init();

    Website.init('./client/');
    
    await Services.init();
    await Services.registerServices();

    Logger.ready();
}
