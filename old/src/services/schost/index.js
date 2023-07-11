const Database = require('./database.js');
const Router = require('./router.js')

let Logger;

module.exports.main = async function(service, logger) {
    logger.info("Service SCHost initializng...");
    Logger = logger;
    
    await Database.init(Logger);
}
