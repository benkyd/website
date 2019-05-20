const Database = require('./database.js');

module.exports.Service;
module.exports.Logger;

module.exports.main = async function(service, logger) {
    logger.info('Service ShortURL initializng...');

    await Database.init(logger);

    module.exports.Service = service;
    module.exports.Logger = logger;

    logger.info('Initialized');
}
