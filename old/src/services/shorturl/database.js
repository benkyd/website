const Sequelize = require('sequelize');

const fs = require('fs');

let Logger;

module.exports.init = async function(logger) {
    Logger = logger;

    if (!fs.existsSync('./storage'))
        fs.mkdirSync('./storage');

    Logger.info('Connecting to SQLite Database');
    module.exports.connection = new Sequelize('database', 'user', 'password', {
        host: 'localhost',
        dialect: 'sqlite',
        logging: logger.database,
        operatorsAliases: false,
        storage: 'storage/shorturl.sqlite',
    });

    module.exports.UrlShort = module.exports.connection.define('shorturl', {
        endpoint: {
            type: Sequelize.TEXT,
            primaryKey: true,
            unique: true
        },
        target: {
            type: Sequelize.TEXT,
            unique: true
        },
        uses: Sequelize.BIGINT
    }, {
        tableName: 'shorturl'
    });

    try {
        await module.exports.connection.sync({force: false});
    } catch (e) {
        Logger.error(`Failed to connect shorturl to SQLite Database, error: ${e}`);
        return;
    }
    Logger.info(`Connected to SQLite Database`);
}

module.exports.getAll = async function() {
    let UrlShort = module.exports.UrlShort;
    return UrlShort.findAll();
}

module.exports.newURL = async function(endpoint, url) {
    let UrlShort = module.exports.UrlShort;

    try {
        let Url = await UrlShort.create({
            endpoint: endpoint,
            target: url,
            uses: 0
        });
        return Url;
    } catch (e) {
        Logger.error(`An error occured while inserting ${endpoint} and ${url} into the UrlShort table: ${JSON.stringify(e.errors)}`);
        return -1;
    }
}

module.exports.getURLFromEndpoint = async function(endpoint) {
    let UrlShort = module.exports.UrlShort;

    try {
        let ret = await UrlShort.findOne({where: {endpoint: endpoint}});
        if (ret == null) return -1;
        return ret;
    } catch (e) {
        Logger.error(`An error occured while querying the UrlShort table with ${endpoint}: ${JSON.stringify(e.errors)}`);
        return -1;
    }
}

module.exports.getEndpointFromURL = async function(url) {
    let UrlShort = module.exports.UrlShort;
    
    try {
        let ret = await UrlShort.findOne({where: {target: url}});
        if (ret == null) return -1;
        return ret;
    } catch (e) {
        Logger.error(`An error occured while querying the UrlShort table with ${url}: ${JSON.stringify(e.errors)}`);
        return -1;
    }
}

module.exports.incrementUses = async function(count, endpoint) {
    let UrlShort = module.exports.UrlShort;

    try {
        UrlShort.update({uses: count}, {where: {endpoint: endpoint}});
        return 1;
    } catch (e) {
        Logger.error(`An error occured while updating the UrlShort table with ${endpoint}: ${JSON.stringify(e.errors)}`);
        return -1;
    }
}
