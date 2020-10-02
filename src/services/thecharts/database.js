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
        storage: 'storage/thechart.sqlite',
    });

    module.exports.UrlShort = module.exports.connection.define('groups', {
        
    }, {
        tableName: 'thechart'
    });

    try {
        await module.exports.connection.sync({force: false});
    } catch (e) {
        Logger.error(`Failed to connect TheChart to SQLite Database, error: ${e}`);
        return;
    }
    Logger.info(`Connected to SQLite Database`);
}
