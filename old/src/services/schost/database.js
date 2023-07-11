const Sequelize = require('sequelize');

const fs = require('fs');

let Logger;

module.exports.imageStorage = './storage/schost/';

module.exports.init = async function(logger) {
    Logger = logger;

    if (!fs.existsSync('./storage'))
         fs.mkdirSync('./storage');

    if (!fs.existsSync(module.exports.imageStorage)) {
        Logger.error('Can\'t find the storage helper in storage/schost/storageHelper.js, aborting');
        return;
    }

    Logger.info('Connecting to SQLite Database');
    module.exports.connection = new Sequelize('database', 'user', 'password', {
        host: 'localhost',
        dialect: 'sqlite',
        logging: logger.database,
        operatorsAliases: false,
        storage: 'storage/schost.sqlite',
    });

    module.exports.ScHost = module.exports.connection.define('schost', {
        id: {
            type: Sequelize.TEXT,
            primaryKey: true,
            unique: true
        }
    }, {
        tableName: 'schost'
    });

    try {
        await module.exports.connection.sync({force: false});
    } catch (e) {
        Logger.error(`Failed to connect shorturl to SQLite Database, error: ${e}`);
        return;
    }
    Logger.info(`Connected to SQLite Database`);
}

// Returns false if nothing is found, true if something is
module.exports.checkID = async function(id) {
    let ScHost = module.exports.ScHost;

    try {
        let ret = await ScHost.findOne({where: {id: id}});
        if (ret == null) return false;
        return true;
    } catch (e) {
        Logger.error(`An error occured while querying the ScHost table with ${id}: ${JSON.stringify(e.errors)}`);
        return -1;
    }
}

module.exports.newImage = async function(id) {
    let ScHost = module.exports.ScHost;

    try {
        let sc = await ScHost.create({
            id: id,
        });
        return sc;
    } catch (e) {
        Logger.error(`An error occured while inserting ${id} into the ScHost table: ${JSON.stringify(e.errors)}`);
        return -1;
    }
}
