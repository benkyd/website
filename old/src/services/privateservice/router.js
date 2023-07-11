const express = require('express');
const router = express.Router();

const Middleware = require('../../middlewares/authenticator.js');

router.get('/', [Middleware.authenticator, async (req, res, next) => {
    res.send('bruh')
}]);

module.exports = router;
