const Sequelize = require('sequelize');
const fs = require('fs');

const Logger = require('../logger.js');

module.exports.init = async function() {
    if (!fs.existsSync('./storage'))
         fs.mkdirSync('./storage');

    Logger.middleware('auth', 'Connecting to SQLite Database');
    module.exports.connection = new Sequelize('database', 'user', 'password', {
        host: 'localhost',
        dialect: 'sqlite',
        logging: Logger.database,
        operatorsAliases: false,
        storage: 'storage/authentication.sqlite',
    });

    module.exports.users = module.exports.connection.define('users', {
        id: {
            type: Sequelize.BIGINT,
            primaryKey: true,
            unique: true
        },
        username: Sequelize.TEXT,
        password: Sequelize.TEXT,
        email: Sequelize.TEXT,
        ip: Sequelize.TEXT,
        lastupdated: Sequelize.TEXT,
        verified: Sequelize.BOOLEAN,
        password: Sequelize.TEXT,
        token: Sequelize.TEXT,
        timeauthed: Sequelize.TEXT
    }, {
        tableName: 'users'
    });

    try {
        await module.exports.connection.sync({force: false});
    } catch (e) {
        Logger.error(`Failed to connect shorturl to SQLite Database, error: ${e}`);
        return;
    }
    Logger.middleware('auth', 'Connected to SQLite Database');
}
