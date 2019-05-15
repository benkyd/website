const Logger = require('../../logger.js');
const Database = require('./database.js');

module.exports.service;

module.exports.main = async function(service, router) {
    Logger.service(service.name, "Service ShortURL initializng...");
    await Database.init(service);
    module.exports.service = service;
    Logger.service(service.name, 'Initialized');
}
