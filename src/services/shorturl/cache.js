const Database = require('./database.js');

const cacheAmount = 50000;

let cache = [];

let Logger;

module.exports.init = async function(logger) {
    Logger = logger;

    cache = []

    Logger.info('Setting up cache... This may take some time...');
    let allEntries = await Database.getAll();

    for (entry of allEntries) {
        cache.push({
            endpoint: entry.endpoint,
            target: entry.target,
            uses: entry.uses
        });
    }

    cache.sort((a, b) => (b.uses - a.uses));

    for (c of cache) {
        logger.debug(JSON.stringify(c));
    }

    allEntries = undefined;
    
    Logger.info('Cache ready');
}

module.exports.update = async function() {

}

module.exports.checkCacheByEndpoint = async function(endpoint) {

}

module.exports.checkCacheByTarget = async function(target) {

}

function findEntryByEndpoint(endpoint) {
    for (c of cache)
        if (c.endpoint === endpoint) return c;
    return undefined;
}

function findEntryByTarget(target) {
    for (c of cache)
        if (c.target === target) return c;
    return undefined;
}

