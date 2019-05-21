const Database = require('./database.js');
const Router = require('./router.js');
const Cache = require('./cache.js');

module.exports.Service;
module.exports.Logger;

module.exports.main = async function(service, logger) {
    logger.info('Service ShortURL initializng...');

    await Database.init(logger);
    await Cache.init(logger);
    // await Router.init(logger);

    module.exports.Service = service;
    module.exports.Logger = logger;


    logger.info('Initialized');
}
