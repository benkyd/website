const Logger = require('./logger.js');


module.exports.init = async function() {
    Logger.info('Initialized service handle')
}

module.exports.registerServices = async function() {
    Logger.info('Registering services');
}
