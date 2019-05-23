const Database = require('./database.js');

const cacheAmount = 10000;
const updateThreshold = 1;

let cache = [];

let Logger;

module.exports.init = async function(logger) {
    Logger = logger;

    cache = []

    Logger.info('Setting up cache');
    let allEntries = await Database.getAll();

    for (entry of allEntries) {
        cache.push({
            endpoint: entry.endpoint,
            target: entry.target,
            uses: entry.uses
        });
    }

    cache.sort((a, b) => (b.uses - a.uses));

    if ((cache.length > cacheAmount))
        cache.splice(cacheAmount, cache.length);

    allEntries = undefined;

    Logger.info('Cache ready');

}

let updateCounter = 0;
module.exports.update = async function() {
    updateCounter++;
    if (updateCounter > updateThreshold)
        updateCounter = 0;
    else
        return;

    cache = []

    Logger.info('Updating cache');
    let allEntries = await Database.getAll();

    for (entry of allEntries) {
        cache.push({
            endpoint: entry.endpoint,
            target: entry.target,
            uses: entry.uses
        });
    }

    cache.sort((a, b) => (b.uses - a.uses));

    if ((cache.length > cacheAmount))
        cache.splice(cacheAmount, cache.length);

    allEntries = undefined;

    Logger.info('Cache updated');
}

module.exports.checkCacheByEndpoint = async function(endpoint) {
    let ret = findEntryByEndpoint(endpoint);
    Logger.debug(`Cache checked for ${endpoint}`);
    return ret;
}

module.exports.checkCacheByTarget = async function(target) {
    let ret = findEntryByTarget(target);
    Logger.debug(`Cache checked for ${target}`);
    return ret;
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

