const Logger = require('../../logger.js');

module.exports.main = async function(service, router) {
    Logger.service(service.name, "Service ShortURL initializng...");
}
