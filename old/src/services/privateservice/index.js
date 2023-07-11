let Logger;

module.exports.main = async function(service, logger) {
    logger.info("Service private initializng...");
    Logger = logger;
}
