const Database = require('./database.js');
const Controller = require('./controller.js');

const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');''
const base64Img = require('base64-img');

const router = express.Router();

router.get('/', async (req, res) => {
    res.sendFile(__dirname + '/client/index.html');
});

router.post('/', async (req, res) => {
    let img = req.body.img;
    if (!img) return;

    let name = await Controller.genEndpoint();

    let nName = await base64Img.imgSync(img, Database.imageStorage, name);

    
    if (nName.includes('/')) {
        nName = nName.split('/')
    } else {
        nName = nName.split('\\');
    }

    
    nName = nName[nName.length - 1]

    Database.newImage(nName);

    res.send(JSON.stringify({ url: nName }));
});

module.exports = router;
