const Logger = require('../../logger.js');

const Sequelize = require('sequelize');

let Service;

module.exports.init = async function(service) {
    Service = service;

    Logger.service(service.name, 'Connecting to SQLite Database');
    module.exports.connection = new Sequelize('database', 'user', 'password', {
        host: 'localhost',
        dialect: 'sqlite',
        logging: Logger.database,
        operatorsAliases: false,
        storage: 'storage/shorturl.sqlite',
    });

    module.exports.UrlShort = module.exports.connection.define('UrlShort', {
        endpoint: {
            type: Sequelize.TEXT,
            primaryKey: true,
            unique: true
        },
        target: Sequelize.TEXT
    }, {
        tableName: 'UrlShort'
    });

    try {
        await module.exports.connection.sync({force: false});
    } catch (e) {
        Logger.serviceError(service.name,`Failed to connect ${service.name} to SQLite Database, error: ${e}`);
    }
    Logger.service(service.name, `Connected to SQLite Database`);
}

module.exports.newURL = async function(endpoint, url) {
    let UrlShort = module.exports.UrlShort;

    try {
        let Url = await UrlShort.create({
            endpoint: endpoint,
            target: url
        });
        return Url;
    } catch (e) {
        Logger.serviceError(Service.name, `An error occured while inserting ${endpoint} and ${url} into the UrlShort table: ${JSON.stringify(e.errors)}`);
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
        Logger.serviceError(Service.name, `An error occured while querying the UrlShort table with ${endpoint}: ${JSON.stringify(e.errors)}`);
        return -1;
    }
}
