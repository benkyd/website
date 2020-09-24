module.exports.Service;
module.exports.Logger;

module.exports.main = async function(service, logger) {

    logger.info('Service VideoHost initializing...');

    module.exports.Service = service;
    module.exports.Logger = service;

    logger.info('Initialized');

}
